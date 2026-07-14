# Writing sensor drivers from a datasheet

How to turn an I2C or SPI sensor datasheet into a working S2 Module Lua driver. Every API call below exists verbatim in the Superstack Lua Library Reference — do not invent functions, options, or return fields beyond these.

## Hardware facts you must respect

- **Valid pins (18 total):** `A0 A1 B0 B1 C0 C1 C2 C3 C4 D0 D1 D2 D3 D4 E0 E1 F0 F1`
- **Analog-capable pins ONLY:** `C2 C3 C4 D0 D1 D2 D3 D4`
- **I2C `port` option is valid ONLY on `"PORTA"`, `"PORTB"`, `"PORTE"`, `"PORTF"`** (Qwiic/STEMMA QT pinout: pin 3 = SDA = `x0`, pin 4 = SCL = `x1`, e.g. PORTA is SDA=`A0`, SCL=`A1`). For sensors wired to PORTC or PORTD pins you must pass explicit `scl_pin=` and `sda_pin=` instead — never `port="PORTC"` or `port="PORTD"`.
- **Power:** VOUT1 feeds ports A/B/C; VOUT2 feeds D/E/F. Both rails always track the same voltage. `device.power.set_vout(v)` sets ALL ports at once, 1.8–3.3 V in 0.1 V steps, 100 mA per rail. **The rails boot live at 1.8 V** — a 3.3 V sensor on an unconfigured port half-works with marginal I2C signaling rather than failing cleanly, so always `device.power.set_vout(3.3)` before first sensor contact.
- **`device.sleep(t)` takes SECONDS** (e.g. `device.sleep(0.01)` = 10 ms). Datasheet conversion times are usually in ms — divide by 1000.
- **I2C return values differ by call.** `read` and `write_read` return `{ success, data, value }`; `write` returns `{ success }` only (no `data`/`value`); `scan` returns `nil` — its results appear in the logs, so there's nothing to check. Always check `.success` after `read`, `write_read`, and `write`. SPI, UART, analog, and digital calls have **no** success flag — validate SPI sensors by reading a known ID register instead.
- No `io`, `os`, or `debug` in the sandbox (a minimal undocumented `require` exists but re-executes modules on every call — prefer single-file drivers). The script restarts from the top on every code push, save, or reboot, so init sequences must be idempotent.

## The methodology

### 1. Find the 7-bit I2C address

Datasheets sometimes list the 8-bit (shifted) address — the Lua API wants the **7-bit** address (e.g. SHT45 is `0x44`, not `0x88`). If unsure, run a scan and read the log:

```lua
device.power.set_vout(3.3)
device.sleep(0.1)
device.i2c.scan({ port="PORTA" })
```

### 2. Register reads: write-then-read

The universal pattern for "read register `reg` of length `n`":

```lua
local result = device.i2c.write_read(addr, "\x06", 2, { port="PORTA" })
if result.success then
    print(result.value)  -- first byte, handy for 1-byte reads
end
```

`write_read` performs the register-pointer write and the read as one transaction. Some sensors (e.g. VCNL4040) misbehave with a repeated start; for those, split it into `device.i2c.write(addr, "\x09", {...})` followed by `device.i2c.read(addr, 2, {...})`, checking `.success` on both.

For command-based sensors (Sensirion style), write the command, wait the datasheet conversion time with `device.sleep`, then read:

```lua
if not device.i2c.write(0x44, "\xFD", { port="PORTA" }).success then  -- trigger measurement
    print("I2C write failed")
end
device.sleep(0.01)                                 -- 8.3 ms max conversion
local result = device.i2c.read(0x44, 6, { port="PORTA" })
```

### 3. Multi-byte assembly and endianness

`result.data` is a Lua string; extract bytes with `string.byte(result.data, i)` (1-indexed) or the method form `result.data:byte(i)`. Check the datasheet for byte order:

```lua
-- Big-endian (MSB first — Sensirion, MCP9808, most Bosch regs)
local raw = (string.byte(result.data, 1) << 8) | string.byte(result.data, 2)

-- Little-endian (LSB first — VCNL4040, ENS160 data registers)
local raw = string.byte(result.data, 1) | (string.byte(result.data, 2) << 8)

-- 20-bit value packed across 3 bytes (BMP280 raw ADC)
local adc = (string.byte(result.data, 1) * 65536 + string.byte(result.data, 2) * 256 + string.byte(result.data, 3)) // 16
```

### 4. Two's-complement sign handling

Lua integers are 64-bit, so a raw 16-bit read is always positive. Convert signed fields manually:

```lua
local function s16(v)
    if v > 32767 then v = v - 65536 end
    return v
end

local function s8(v)
    if v > 127 then v = v - 256 end
    return v
end
```

For values where the sign lives in a flag bit (e.g. MCP9808 bit 4 of the upper byte), mask the magnitude and subtract the range when the sign bit is set — see the MCP9808 driver below.

### 5. Scaling and calibration math

Apply the datasheet transfer function *after* assembly and sign conversion. Three common shapes:

- **Linear formula** (SHT45): `T = -45 + 175 * raw / 65535`
- **Fixed-point LSB** (MCP9808): `T = twelve_bit_value / 16.0`
- **Factory calibration coefficients read from the chip** (BMP280): read the calibration block once at startup, then run the vendor's compensation algorithm on every sample — see the BMP280 driver below.

### 6. CRC checking (Sensirion SHT4x and friends)

Sensirion sensors append a CRC-8 byte after every 16-bit word (polynomial `0x31`, init `0xFF`, no reflection, no final XOR). The official air-quality-monitor blog example **skips CRC validation** — fine for a demo, but a production driver should verify it, since I2C `.success` only tells you the bus transaction completed, not that the bits are clean:

```lua
-- CRC-8, polynomial 0x31, init 0xFF (Sensirion SHT4x, SGP4x, SCD4x...)
local function crc8(data, first, last)
    local crc = 0xFF
    for i = first, last do
        crc = crc ~ string.byte(data, i)
        for _ = 1, 8 do
            if crc & 0x80 ~= 0 then
                crc = ((crc << 1) & 0xFF) ~ 0x31
            else
                crc = (crc << 1) & 0xFF
            end
        end
    end
    return crc
end

-- A 6-byte SHT4x frame is: T_msb T_lsb T_crc H_msb H_lsb H_crc
local ok = crc8(d, 1, 2) == string.byte(d, 3) and crc8(d, 4, 5) == string.byte(d, 6)
```

### 7. Init, reset, and conversion delays

- Power the rail first, then wait for it to settle: `device.power.set_vout(3.3)` then `device.sleep(0.1)`.
- Probe a chip-ID / manufacturer-ID register before configuring anything, and `error()` with a helpful message if it's wrong — this catches wiring and address mistakes immediately in the Superstack logs.
- Send the datasheet soft-reset command if the sensor has one, then wait the documented startup time. Remember the script re-runs from the top on every push, so the sensor may already be configured — resets make re-runs deterministic.
- All delays go through `device.sleep(seconds)`. A "10 ms conversion time" is `device.sleep(0.01)`, not `device.sleep(10)`.

---

## Worked driver 1: SHT45 temperature + humidity (with proper CRC)

Wiring: Qwiic cable to **PORTA** (SDA=A0, SCL=A1). 7-bit address `0x44`. This is the same sensor as the official blog example, but with `.success` checks and CRC validation added.

```lua
-- SHT45 temperature and humidity, address 0x44, Qwiic on PORTA
local SHT45_ADDRESS = 0x44

device.power.set_vout(3.3)
device.sleep(0.1)

-- CRC-8, polynomial 0x31, init 0xFF (Sensirion)
local function crc8(data, first, last)
    local crc = 0xFF
    for i = first, last do
        crc = crc ~ string.byte(data, i)
        for _ = 1, 8 do
            if crc & 0x80 ~= 0 then
                crc = ((crc << 1) & 0xFF) ~ 0x31
            else
                crc = (crc << 1) & 0xFF
            end
        end
    end
    return crc
end

-- Soft reset (0x94), 1 ms max reset time
if not device.i2c.write(SHT45_ADDRESS, "\x94", { port="PORTA" }).success then
    error("No response from address 0x44. Check the wiring and port")
end
device.sleep(0.01)

-- Returns temperature (C) and relative humidity (%), or nil on failure
local function sht45_measure()
    -- 0xFD = measure with high repeatability, 8.3 ms max conversion
    if not device.i2c.write(SHT45_ADDRESS, "\xFD", { port="PORTA" }).success then
        return nil
    end
    device.sleep(0.01)

    local result = device.i2c.read(SHT45_ADDRESS, 6, { port="PORTA" })
    if not result.success then
        return nil
    end

    local d = result.data

    -- Frame: T_msb T_lsb T_crc H_msb H_lsb H_crc. Validate both CRCs
    if crc8(d, 1, 2) ~= string.byte(d, 3) or crc8(d, 4, 5) ~= string.byte(d, 6) then
        return nil
    end

    -- Big-endian raw words, then the datasheet linear transfer functions
    local raw_t = (string.byte(d, 1) << 8) | string.byte(d, 2)
    local raw_h = (string.byte(d, 4) << 8) | string.byte(d, 5)

    local temperature = -45 + 175 * (raw_t / 65535)
    local humidity = -6 + 125 * (raw_h / 65535)

    -- The formula can stray slightly outside 0-100 at the extremes
    if humidity < 0 then humidity = 0 end
    if humidity > 100 then humidity = 100 end

    return temperature, humidity
end

while true do
    local temperature, humidity = sht45_measure()

    if temperature then
        network.send_data {
            temperature_celsius = temperature,
            humidity_percent = humidity
        }
    else
        print("SHT45 read failed (bus error or CRC mismatch)")
    end

    device.sleep(10)
end
```

---

## Worked driver 2: MCP9808 precision temperature (sign-flag handling)

Wiring: Qwiic cable to **PORTB** (SDA=B0, SCL=B1). 7-bit address `0x18` (A0/A1/A2 straps select 0x18–0x1F). Based on the official `adafruit_mcp9808.lua` example. Demonstrates ID probing and a sign bit embedded in a flag byte.

```lua
-- MCP9808 temperature, address 0x18, Qwiic on PORTB
local MCP9808_ADDRESS = 0x18

device.power.set_vout(3.3)
device.sleep(0.1)

-- Probe the manufacturer ID register (0x06), which always reads 0x00 0x54
local id = device.i2c.write_read(MCP9808_ADDRESS, "\x06", 2, { port="PORTB" })

if not id.success then
    error("No response from address 0x18. Check the wiring and port")
end

if id.data:byte(1) ~= 0x00 or id.data:byte(2) ~= 0x54 then
    error("Unexpected manufacturer ID. Expected 0x00 0x54")
end

-- Returns temperature in C, or nil on failure
local function mcp9808_measure()
    -- Ambient temperature register (0x05), big-endian
    local result = device.i2c.write_read(MCP9808_ADDRESS, "\x05", 2, { port="PORTB" })
    if not result.success then
        return nil
    end

    local upper = result.data:byte(1)
    local lower = result.data:byte(2)

    -- Upper 3 bits are alert flags, bit 4 is the sign, leaving a 12-bit
    -- magnitude in steps of 1/16 C
    local temperature = ((upper & 0x0F) * 256 + lower) / 16.0

    -- Two's complement when the sign bit is set
    if upper & 0x10 ~= 0 then
        temperature = temperature - 256
    end

    return temperature
end

while true do
    local temperature = mcp9808_measure()

    if temperature then
        network.send_data { temperature_celsius = temperature }
    else
        print("MCP9808 read failed")
    end

    device.sleep(5)
end
```

---

## Worked driver 3: BMP280 pressure (on-chip calibration coefficients)

Wiring: **PORTC has no `port=` shortcut** — this driver shows the explicit-pin form, SCL=C0, SDA=C1. 7-bit address `0x77` (`0x76` if SDO is pulled low). Based on the official `adafruit_bmp280.lua` example. Demonstrates reading a factory calibration block once and running the vendor compensation algorithm per sample.

```lua
-- BMP280 pressure and temperature, address 0x77, wired to C0 (SCL) / C1 (SDA)
local BMP280_ADDRESS = 0x77
local I2C_OPTS = { scl_pin="C0", sda_pin="C1" }

device.power.set_vout(3.3)
device.sleep(0.1)

local function read_reg(reg, len)
    local result = device.i2c.write_read(BMP280_ADDRESS, string.char(reg), len or 1, I2C_OPTS)
    if not result.success then return nil end
    return result.data
end

-- Probe the chip ID register (0xD0), which always reads 0x58
local id = read_reg(0xD0)
if not id then
    error("No response from address 0x77. Check the wiring")
end
if string.byte(id, 1) ~= 0x58 then
    error("Unexpected chip ID. Expected 0x58")
end

-- Soft reset (write 0xB6 to register 0xE0), then wait for startup
if not device.i2c.write(BMP280_ADDRESS, "\xE0\xB6", I2C_OPTS).success then
    error("I2C write failed during soft reset")
end
device.sleep(0.1)

-- Calibration block: 12 little-endian 16-bit words at 0x88
local cal = read_reg(0x88, 24)
if not cal then
    error("Failed to read calibration data")
end

local function u16(lo, hi) return string.byte(cal, lo) + string.byte(cal, hi) * 256 end
local function s16(lo, hi)
    local v = u16(lo, hi)
    if v > 32767 then v = v - 65536 end
    return v
end

local T1, T2, T3 = u16(1, 2), s16(3, 4), s16(5, 6)
local P1, P2, P3 = u16(7, 8), s16(9, 10), s16(11, 12)
local P4, P5, P6 = s16(13, 14), s16(15, 16), s16(17, 18)
local P7, P8, P9 = s16(19, 20), s16(21, 22), s16(23, 24)

-- Normal mode, temperature and pressure oversampling x1 (register 0xF4)
if not device.i2c.write(BMP280_ADDRESS, "\xF4\x27", I2C_OPTS).success then
    error("I2C write failed during mode configuration")
end
device.sleep(0.1)

-- Bosch datasheet compensation. Returns temperature (C) and pressure (hPa)
local function compensate(adc_T, adc_P)
    local var1 = (adc_T / 16384.0 - T1 / 1024.0) * T2
    local var2 = ((adc_T / 131072.0 - T1 / 8192.0) ^ 2) * T3
    local t_fine = var1 + var2
    local temp = t_fine / 5120.0

    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * P6 / 32768.0
    var2 = var2 + var1 * P5 * 2.0
    var2 = var2 / 4.0 + P4 * 65536.0
    var1 = (P3 * var1 * var1 / 524288.0 + P2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * P1

    local press = 0
    if var1 ~= 0 then
        press = 1048576.0 - adc_P
        press = (press - var2 / 4096.0) * 6250.0 / var1
        var1 = P9 * press * press / 2147483648.0
        var2 = press * P8 / 32768.0
        press = press + (var1 + var2 + P7) / 16.0
    end

    return temp, press / 100.0
end

while true do
    -- Raw pressure and temperature: 20 bits each, packed into 6 bytes at 0xF7
    local raw = read_reg(0xF7, 6)

    if raw then
        local adc_P = (string.byte(raw, 1) * 65536 + string.byte(raw, 2) * 256 + string.byte(raw, 3)) // 16
        local adc_T = (string.byte(raw, 4) * 65536 + string.byte(raw, 5) * 256 + string.byte(raw, 6)) // 16

        local temperature, pressure = compensate(adc_T, adc_P)

        network.send_data {
            temperature_celsius = temperature,
            pressure_hpa = pressure
        }
    else
        print("BMP280 read failed")
    end

    device.sleep(10)
end
```

---

## SPI sensors

Use `device.spi.write_read(write_data, read_length, { ... })`, `device.spi.write(data, { ... })`, `device.spi.read(length, { ... })`, or `device.spi.transact(write_data, read_length, { ... })` (write and read in parallel, full-duplex).

The **only** documented options are: `sclk_pin`, `mosi_pin`, `miso_pin`, `cs_pin`, `mode` (0–3), `frequency` (kHz: 125, 250, 500, 1000, 2000, 4000, or 8000), `bit_order` (`"MSB_FIRST"`/`"LSB_FIRST"`), `hold_cs`, `cs_active_high`, and `miso_pull` (`"PULL_UP"`/`"PULL_DOWN"`/`"NO_PULL"`). Any four valid pins can be used — there is no `port=` shortcut for SPI.

Key differences from I2C:

- **No `success` flag.** `write_read`, `read`, and `transact` return the raw bytes as a string; `write` returns nil. Validate the sensor by reading a known ID register and checking the value.
- Many chips encode read vs. write in the register address MSB (Bosch: reads set bit 7, writes clear it).
- Use `hold_cs=true` for multi-step transactions that must keep CS asserted between calls.

```lua
-- BMP280 in SPI mode: SCLK=D0, MOSI=D1, MISO=D2, CS=D3
local SPI_OPTS = {
    sclk_pin="D0", mosi_pin="D1", miso_pin="D2", cs_pin="D3",
    mode=0, frequency=1000, bit_order="MSB_FIRST"
}

device.power.set_vout(3.3)
device.sleep(0.1)

-- Reads set bit 7 of the register address. Chip ID (0xD0) always reads 0x58.
-- write_read clocks the write out first, then reads — no dummy byte needed
-- (use device.spi.transact for full-duplex chips that reply during the write)
local data = device.spi.write_read("\xD0", 1, SPI_OPTS)

if string.byte(data, 1) ~= 0x58 then
    error("Unexpected chip ID over SPI. Check the wiring")
end

-- Writes clear bit 7: configure register 0xF4 (0xF4 & 0x7F = 0x74)
device.spi.write("\x74\x27", SPI_OPTS)
```
