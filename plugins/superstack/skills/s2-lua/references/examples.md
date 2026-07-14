# Complete example programs

Full, working S2 Module Lua programs. Every API call exists verbatim in the Superstack Lua Library Reference. Remember the ground rules: the script restarts from the top on every code push, save, or reboot; a single file may be at most 100,000 characters; there is no `io`, `os`, or `require`; and there is **no downlink** — no `network.receive`, no MQTT, no webhooks, no remote config. The only way to change device behavior is to push new code, and a push retransmits the whole file to every target device.

## Official examples index (s2-lua-examples repo)

Repository: <https://github.com/siliconwitchery/s2-lua-examples>

Single-sensor drivers:

- [`adafruit_bmp280.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/adafruit_bmp280.lua) — Barometric pressure + temperature; reads the on-chip calibration block and runs the Bosch compensation algorithm.
- [`adafruit_ina237.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/adafruit_ina237.lua) — Voltage, current, and power monitoring on a shunt resistor.
- [`adafruit_mcp9808.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/adafruit_mcp9808.lua) — Precision temperature; demonstrates manufacturer-ID probing and sign-flag handling.
- [`adafruit_mlx90393.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/adafruit_mlx90393.lua) — 3-axis magnetic field strength.
- [`adafruit_vl53l0x.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/adafruit_vl53l0x.lua) — Laser time-of-flight distance measurement.
- [`sparkfun_as7343.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/sparkfun_as7343.lua) — 12-channel spectral light sensing.
- [`sparkfun_cap1203.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/sparkfun_cap1203.lua) — 3-pad capacitive touch input.
- [`sparkfun_vcnl4040.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/sparkfun_vcnl4040.lua) — Ambient light; demonstrates little-endian registers and split write/read transactions.

Complete applications:

- [`air-quality-monitor.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/air-quality-monitor.lua) — SHT45 + ENS160 with cross-sensor calibration and relay-driven fan control (the blog build; note it skips SHT4x CRC validation — see `sensor-drivers.md` for the CRC-checked version).
- [`embedded-world-badge.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/embedded-world-badge.lua) — Conference badge combining temperature, eCO₂, NFC, and a transparent display.
- [`weather-station.lua`](https://github.com/siliconwitchery/s2-lua-examples/blob/main/weather-station.lua) — SHT45 + BMP280 station computing dew point (Magnus formula), sea-level pressure, and a 3-hour pressure-tendency storm forecast with IIR filtering.

---

## Example A: Battery-powered environmental logger with store-and-forward

An SHT45 logger that keeps working through cellular dead zones: while offline, samples are appended to a file in non-volatile storage; when the connection returns, the backlog is drained to Superstack before resuming live reporting.

Data-budget notes:

- Both `print()` logs and `network.send_data` are **billable** traffic. This program prints only on errors and on backlog drains, not per sample.
- Draining sends one message per buffered sample so each keeps its own timestamp. If your budget is tight, aggregate instead (e.g. send min/mean/max per hour of backlog).
- Timestamps come from `time.get_unix_time()`, which returns **milliseconds** (the docs' "wait 30 seconds" example using `t + 30` is a known bug — 30 seconds is `t + 30000`). Before the first network time sync it returns uptime in ms; those samples are flagged so the backend can discard or re-base them.

```lua
-- Battery-powered SHT45 environmental logger with offline buffering.
-- Wiring: SHT45 on PORTA (Qwiic: SDA=A0, SCL=A1). Powered from a 4.2V Li-Po.

local SHT45_ADDRESS = 0x44
local BACKLOG_FILE = "backlog.csv"
local SAMPLE_INTERVAL = 60 -- seconds between samples

-- Configure charging for a 4.2V 200mAh Li-Po cell (termination voltage must
-- be one of the supported steps: 3.50-3.65 or 4.00-4.45; current 32-800mA)
device.power.battery.set_charger_cv_cc(4.2, 200)

-- Power the sensor rail and let it settle
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

-- Returns temperature (C) and humidity (%), or nil on failure
local function sht45_measure()
    if not device.i2c.write(SHT45_ADDRESS, "\xFD", { port="PORTA" }).success then
        return nil
    end
    device.sleep(0.01)

    local result = device.i2c.read(SHT45_ADDRESS, 6, { port="PORTA" })
    if not result.success then
        return nil
    end

    local d = result.data
    if crc8(d, 1, 2) ~= string.byte(d, 3) or crc8(d, 4, 5) ~= string.byte(d, 6) then
        return nil
    end

    local raw_t = (string.byte(d, 1) << 8) | string.byte(d, 2)
    local raw_h = (string.byte(d, 4) << 8) | string.byte(d, 5)

    local temperature = -45 + 175 * (raw_t / 65535)
    local humidity = -6 + 125 * (raw_h / 65535)
    if humidity < 0 then humidity = 0 end
    if humidity > 100 then humidity = 100 end

    return temperature, humidity
end

-- Timestamps below ~year-2001 in ms mean the clock hasn't synced yet and the
-- value is actually device uptime. Flag those samples
local function time_is_synced(ts)
    return ts > 1000000000000
end

local function backlog_exists()
    for _, file in ipairs(storage.list()) do
        if file.name == BACKLOG_FILE then
            return file.size > 0
        end
    end
    return false
end

-- Send every buffered sample, then delete the backlog file. network.send_data
-- gives no delivery confirmation, so this is best-effort: only clear the
-- backlog if the link is still up once the loop finishes, otherwise leave the
-- file in place and retry the whole drain next cycle
local function drain_backlog()
    local contents = storage.read(BACKLOG_FILE)
    local sent = 0

    for line in string.gmatch(contents, "[^\n]+") do
        local ts, temperature, humidity =
            string.match(line, "^(%d+),([%-%.%d]+),([%-%.%d]+)$")

        if ts then
            -- One billable message per buffered sample. Aggregate here
            -- instead if data budget matters more than per-sample timing
            network.send_data {
                buffered = true,
                sampled_at_ms = tonumber(ts),
                clock_synced = time_is_synced(tonumber(ts)),
                temperature_celsius = tonumber(temperature),
                humidity_percent = tonumber(humidity)
            }
            sent = sent + 1
        end
    end

    if network.connected() then
        storage.delete(BACKLOG_FILE)
        print("Drained "..sent.." buffered samples")
    else
        -- Link dropped mid-drain: keep the file and retry next cycle rather
        -- than discarding samples we can't confirm were delivered
        print("Connection dropped mid-drain. Keeping backlog for retry")
    end
end

while true do
    local temperature, humidity = sht45_measure()

    if temperature then
        local now = time.get_unix_time() -- MILLISECONDS, not seconds

        if network.connected() then
            -- Flush any offline backlog first so data arrives in order
            if backlog_exists() then
                drain_backlog()
            end

            network.send_data {
                sampled_at_ms = now,
                clock_synced = time_is_synced(now),
                temperature_celsius = temperature,
                humidity_percent = humidity,
                battery_volts = device.power.battery.get_voltage(),
                battery_status = device.power.battery.get_charging_status()
            }
        else
            -- Offline: append one CSV line per sample to non-volatile storage.
            -- Survives reboots and code restarts
            storage.append(BACKLOG_FILE, string.format(
                "%d,%.2f,%.2f\n", now, temperature, humidity))
        end
    else
        print("SHT45 read failed (bus error or CRC mismatch)")
    end

    device.sleep(SAMPLE_INTERVAL) -- seconds
end
```

To stretch battery life further you can call `network.low_power_mode(true)` between sends — but be aware PSM adds up to **15 minutes of latency to code pushes**; call `network.low_power_mode(false)` and wait up to 15 minutes to restore real-time updates.

---

## Example B: GPS asset tracker

Reports position on a fixed interval. Two hard rules from the docs are baked in:

1. **`location.enable{}` silently activates PSM** so the modem can share hardware with the GPS. From that moment, code pushes from Superstack can stall for up to **15 minutes**. The only recovery is `location.disable()` **and** `network.low_power_mode(false)`, then waiting up to 15 minutes for the modem to re-register.
2. **Avoid network activity while acquiring a fix** — `print()` and `network.send_data` compete with the GPS for the modem and delay acquisition. The wait loop below is deliberately silent.

```lua
-- GPS asset tracker: acquire a fix, then report position periodically.
--
-- WARNING: location.enable{} silently activates PSM (Power Saving Mode).
-- After this runs, code pushes from Superstack may take up to 15 MINUTES to
-- arrive. To restore real-time code updates you must push (and wait) or
-- physically power-cycle, then run:
--     location.disable()
--     network.low_power_mode(false)
-- and wait up to 15 minutes for the modem to re-register.

local REPORT_INTERVAL = 60      -- seconds between position reports
local FIX_TIMEOUT_S = 300       -- give up waiting for first fix after 5 min

-- Configure charging for a 4.2V 400mAh Li-Po pack
device.power.battery.set_charger_cv_cc(4.2, 400)

-- Announce startup BEFORE enabling GPS: once location.enable runs we should
-- stay off the network until the first fix, and PSM latency begins
print("Tracker starting. GPS on, code pushes now take up to 15 min")

-- MEDIUM power saving and a 10 s tracking interval trade fix speed for
-- battery life. Use power_saving="OFF", tracking_interval=1 for fastest fixes
location.enable{ accuracy="HIGH", power_saving="MEDIUM", tracking_interval=10 }

-- Wait for the first fix. NO print() or network.send_data in this loop:
-- network activity competes for the modem and delays acquisition.
-- A wall-clock deadline built from time.get_unix_time() is unsafe here:
-- before the first network time sync it returns device uptime in ms, and if
-- the sync lands mid-wait the value jumps forward by decades, blowing past
-- any deadline instantly. Count fixed 10 s sleeps instead so a mid-wait time
-- jump can't shorten or skip the wait
for _ = 1, FIX_TIMEOUT_S // 10 do
    if location.get_latest().valid then
        break
    end
    device.sleep(10) -- seconds
end

if location.get_latest().valid then
    print("First fix acquired")
else
    -- Keep going anyway: the loop below only reports valid fixes, and GPS
    -- keeps searching in the background
    print("No fix within timeout. Continuing to search")
end

while true do
    local l = location.get_latest()

    if l.valid then
        network.send_data {
            latitude = l.latitude,
            longitude = l.longitude,
            altitude_m = l.altitude,
            accuracy_m = l.accuracy,
            speed = l.speed,
            speed_accuracy = l.speed_accuracy,
            satellites_in_fix = l.satellites.in_fix,
            battery_volts = device.power.battery.get_voltage(),
            battery_status = device.power.battery.get_charging_status()
        }
    else
        -- Stale/invalid fix (e.g. indoors). Skip the send to save data;
        -- an occasional heartbeat could go here instead
        print("No valid fix this interval")
    end

    device.sleep(REPORT_INTERVAL) -- seconds
end
```

Deployment tip: because there is no downlink and pushes are PSM-delayed, test tracker code on a bench unit with GPS *disabled* first, and only enable `location` in the final field build. Every code push retransmits the entire file to every target device, so keep the file lean.
