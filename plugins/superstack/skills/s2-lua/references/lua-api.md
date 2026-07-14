<!--
  GENERATED FILE - DO NOT EDIT BY HAND.
  Generated from pages/superstack/lua.md in the siliconwitchery/docs repo by
  scripts/generate-references.py. To update, edit the docs and run:
      python3 scripts/generate-references.py --docs <docs-checkout> --write
-->

# Superstack Lua Library Reference

---

Superstack devices such as the S2 Module run Lua—an incredibly lightweight, efficient and simple to learn language.

The built-in Lua libraries provide complete hardware and network level functionality to **read sensors**, **report data**, **compute on-device algorithms** and take actions such as **driving IO** automatically.

The Lua engine is almost as performant as writing native C firmware as it's a lightweight wrapper around native C functions built into the Superstack firmware.

Compared to writing firmware, the Superstack Lua engine allows for remote and realtime development of IoT code without the need for compiler tools, hardware debuggers or physical access to the device. There's also no risk of bricking devices as Lua runs in a container, and is always updatable and isolated from sensitive internal functions such as network management.

Complete ready-to-run scripts are available in the example repository, and if you write code with an AI assistant, our plugin for Claude teaches it this entire reference.

---

## Contents

- [Coding principles and notation](#coding-principles-and-notation)
- [Standard libraries](#standard-libraries)
- [Hardware libraries](#hardware-libraries)
  - [Digital IO](#digital-io)
  - [Analog input](#analog-input)
  - [I2C communication](#i2c-communication)
  - [SPI communication](#spi-communication)
  - [UART communication](#uart-communication)
- [Networking libraries](#networking-libraries)
  - [Networking (LTE)](#networking-lte)
  - [Location (GPS)](#location-gps)
- [System libraries](#system-libraries)
  - [Logging](#logging)
  - [Sleep](#sleep)
  - [Power](#power)
  - [File storage](#file-storage)
  - [Timekeeping](#timekeeping)
  - [Device information](#device-information)

---

## Coding principles and notation

The functions described in this reference typically represent single, atomic operations. For example `device.digital.set_output()` will output a high, or low voltage on a specified pin. Unlike most hardware level programming, a separate configuration step isn't needed. All configuration is optional and is passed directly into this function if desired.

The functions may accept a combination of **positional** and **named** arguments. Positional arguments always come first, with the named arguments provided at the end as a Lua table of key-value pairs.

Most of the named arguments will take on a default value if not provided. These are marked as _optional_.

```lua
-- Calling a function with only positional arguments
device.digital.set_output("A0", true)

-- Calling a function with both positional and named arguments
device.i2c.write(0x12, "\x4F\x01", { scl_pin="B0", sda_pin="B1" })

-- Calling a function with only named arguments. Note how the () can be omitted
network.send_data{ sensor_value=31.5 }
```

---

## Standard libraries

The device runs **Lua 5.5**. Most of the standard Lua libraries that you would find on the desktop installation of Lua are included:

- ✅ [Basic functions](https://www.lua.org/manual/5.5/manual.html#6.1)
- ✅ [Math functions](https://www.lua.org/manual/5.5/manual.html#6.7)
- ✅ [String manipulation](https://www.lua.org/manual/5.5/manual.html#6.4)
- ✅ [Table manipulation](https://www.lua.org/manual/5.5/manual.html#6.6)
- ✅ [UTF-8 support](https://www.lua.org/manual/5.5/manual.html#6.5)
- ✅ [Coroutine manipulation](https://www.lua.org/manual/5.5/manual.html#6.2)

The remaining standard libraries are not included, as they are superseded by similar functionality provided by the device specific libraries:

- ❎ Debug library

- ❎ File IO functions - Replaced by the [file storage](#file-storage) library
- ❎ Operating system functions - Replaced by the [timekeeping](#timekeeping) and [device information](#device-information) libraries

---

## Hardware libraries

### Digital IO

#### Set or clear a digital output on a pin

```lua
device.digital.set_output(pin, value)
```

**Parameters**

- `pin` - **string** - The pin name. E.g. `"A0"`
- `value` - **boolean** - The level to set. `true` for high, `false` for low

**Returns**

- **nil**

**Example**

```lua
-- Set pin B1 to a high value
device.digital.set_output("B1", true)
```

---

#### Get the digital value on a pin

```lua
device.digital.get_input(pin, { pull="PULL_DOWN" })
```

**Parameters**

- `pin` - **string** - The pin name. E.g. `"A0"`

**Optional parameters**

- `pull` - **string** - The pull mode on the pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **boolean** - `true` if the pin is high, `false` if low

**Example**

```lua
-- Print the value on pin D0
local val = device.digital.get_input("D0")
print(val)
```

---

#### Assign an event handler for a pin input change

```lua
device.digital.assign_input_event(pin, handler, { pull="PULL_DOWN" })
```

**Parameters**

- `pin` - **string** - The pin name. E.g. `"A0"`
- `handler` - **function** - The function to call when the pin value changes. Called with two arguments:
    - `pin` - **string** - The pin name that generated the event. E.g. `"A0"`
    - `state` - **boolean** - The pin value when the event occurred. `true` if high, `false` if low

**Optional parameters**

- `pull` - **string** - The pull mode on the pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **nil**

**Example**

```lua
-- Assign a function that triggers when the input value of C3 changes
function my_pin_handler(pin, state)
    if state == true then
        print(pin.." went high")
    else
        print(pin.." went low")
    end
end

device.digital.assign_input_event("C3", my_pin_handler)
```

---

#### Disable an input event handler on a pin

```lua
device.digital.unassign_input_event(pin)
```

**Parameters**

- `pin` - **string** - The pin name. E.g. `"A0"`

**Returns**

- **nil**

**Example**

```lua
-- Disable the event and detach the pin from the handler
device.digital.unassign_input_event("C3")
```

---

### Analog input

#### Read the analog value on a pin

```lua
device.analog.get_input(pin, { acquisition_time=10 })
```

**Parameters**

- `pin` - **string** - The pin name. Must be an analog capable pin. E.g. `"D0"`

**Optional parameters**

- `acquisition_time` - **integer** - The measurement time in microseconds. Can be `3`, `5`, `10`, `15`, `20`, or `40`. Higher values support greater source resistances (10kΩ, 40kΩ, 100kΩ, 200kΩ, 400kΩ, 800kΩ respectively)

**Returns**

- **number** - The voltage present on the pin in volts

**Example**

```lua
-- Read the analog voltage on pin D0
local voltage = device.analog.get_input("D0")
print(voltage)
```

---

#### Read the differential analog value across two pins

```lua
device.analog.get_differential_input(positive_pin, negative_pin, { acquisition_time=10 })
```

**Parameters**

- `positive_pin` - **string** - The pin name of the positive pin. Must be an analog capable pin. E.g. "D0"
- `negative_pin` - **string** - The pin name of the negative pin. Must be an analog capable pin, and different from `positive_pin`. E.g. "D1"

**Optional parameters**

- `acquisition_time` - **integer** - The measurement time in microseconds. Can be `3`, `5`, `10`, `15`, `20`, or `40`. Higher values support greater source resistances (10kΩ, 40kΩ, 100kΩ, 200kΩ, 400kΩ, 800kΩ respectively)

**Returns**

- **number** - The voltage present across the pins in volts

**Example**

```lua
-- Read the differential analog voltage across pins D0 and D1
local voltage = device.analog.get_differential_input("D0", "D1")
print(voltage)
```

---

### I2C communication

**Note:** A single I2C transaction may read or write at most **8191 bytes**.

#### Read bytes from an I2C device

```lua
device.i2c.read(address, length, { port="PORTA", scl_pin="A1", sda_pin="A0", frequency=100 })
```

**Parameters**

- `address` - **integer** - The 7-bit address of the I2C device
- `length` - **integer** - The number of bytes to read

**Optional parameters**

- `port` - **string** - The 4-pin port the I2C device is connected to. Can be `"PORTA"`, `"PORTB"`, `"PORTE"`, or `"PORTF"`. Assumes [Stemma QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/what-is-stemma)/[Qwiic](https://www.sparkfun.com/qwiic) pinout. For a different pin order, use `scl_pin` and `sda_pin` instead
- `scl_pin` - **string** - The pin name for the SCL signal. E.g. `"C3"`. Must be used with `sda_pin`. Cannot be used with `port`
- `sda_pin` - **string** - The pin name for the SDA signal. E.g. `"C4"`. Must be used with `scl_pin`. Cannot be used with `port`
- `frequency` - **integer** - The I2C frequency in kHz. Can be `100`, `250`, or `400`

**Returns**

- **table** - A table of key-value pairs:
    - `success` - **boolean** - `true` if the transaction was successful, `false` otherwise
    - `data` - **string** - The bytes read. Always of size `length` as specified in the function call
    - `value` - **integer** - The first data byte, useful if only one byte was requested

**Example**

```lua
-- Read multiple bytes from the device and print the fourth byte
local result = device.i2c.read(0x23, 4)

if result.success then
    print(string.byte(result.data, 4))
end
```

---

#### Write bytes to an I2C device

```lua
device.i2c.write(address, data, { port="PORTA", scl_pin="A1", sda_pin="A0", frequency=100 })
```

**Parameters**

- `address` - **integer** - The 7-bit address of the I2C device
- `data` - **string** - The data to write to the device. Can be a hexadecimal string containing zeros. E.g. `"\x1A\x50\x00\xF1"`

**Optional parameters**

- `port` - **string** - The 4-pin port the I2C device is connected to. Can be `"PORTA"`, `"PORTB"`, `"PORTE"`, or `"PORTF"`
- `scl_pin` - **string** - The pin name for the SCL signal. E.g. `"C3"`
- `sda_pin` - **string** - The pin name for the SDA signal. E.g. `"C4"`
- `frequency` - **integer** - The I2C frequency in kHz. Can be `100`, `250`, or `400`

**Returns**

- **table** - A table of key-value pairs:
    - `success` - **boolean** - `true` if the transaction was successful, `false` otherwise

**Example**

```lua
-- Write 0x1234 to the register 0xF9
device.i2c.write(0x23, "\xF9\x12\x34")
```

---

#### Write then read bytes from an I2C device

```lua
device.i2c.write_read(address, write_data, read_length, { port="PORTA", scl_pin="A1", sda_pin="A0", frequency=100 })
```

**Parameters**

- `address` - **integer** - The 7-bit address of the I2C device
- `write_data` - **string** - The data to write to the device. Can be a hexadecimal string containing zeros. E.g. `"\x1A\x50\x00\xF1"`
- `read_length` - **integer** - The number of bytes to read

**Optional parameters**

- `port` - **string** - The 4-pin port the I2C device is connected to. Can be `"PORTA"`, `"PORTB"`, `"PORTE"`, or `"PORTF"`
- `scl_pin` - **string** - The pin name for the SCL signal. E.g. `"C3"`
- `sda_pin` - **string** - The pin name for the SDA signal. E.g. `"C4"`
- `frequency` - **integer** - The I2C frequency in kHz. Can be `100`, `250`, or `400`

**Returns**

- **table** - A table of key-value pairs:
    - `success` - **boolean** - `true` if the transaction was successful, `false` otherwise
    - `data` - **string** - The bytes read. Always of size `read_length` as specified in the function call
    - `value` - **integer** - The first data byte, useful if only one byte was requested

**Example**

```lua
-- Read a byte from register 0x1F on a device with address 0x23
local result = device.i2c.write_read(0x23, "\x1F", 1)

if result.success then
    print(result.value)
end
```

---

#### Scan for I2C devices

```lua
device.i2c.scan({ port="PORTA", scl_pin="A1", sda_pin="A0", frequency=100 })
```

**Optional parameters**

- `port` - **string** - The 4-pin port the I2C device is connected to. Can be `"PORTA"`, `"PORTB"`, `"PORTE"`, or `"PORTF"`
- `scl_pin` - **string** - The pin name for the SCL signal. E.g. `"C3"`
- `sda_pin` - **string** - The pin name for the SDA signal. E.g. `"C4"`
- `frequency` - **integer** - The I2C frequency in kHz. Can be `100`, `250`, or `400`

**Returns**

- **nil**

**Example**

```lua
-- Scan a port for devices
device.i2c.scan({ port="PORTF" })
```

---

### SPI communication

**Note:** The pin options `sclk_pin`, `mosi_pin`, `miso_pin` and `cs_pin` must all be specified together — providing only some of them raises an error. A single transfer may read or write at most **8191 bytes**.

#### Write then read bytes from an SPI device

```lua
device.spi.write_read(write_data, read_length, { sclk_pin="C0", mosi_pin="C1", miso_pin="C2", cs_pin="C3", mode=0, frequency=4000, bit_order="MSB_FIRST", hold_cs=false, cs_active_high=false, miso_pull="NO_PULL" })
```

**Parameters**

- `write_data` - **string** - The data to write to the device
- `read_length` - **integer** - The number of bytes to read from the device

**Optional parameters**

- `sclk_pin` - **string** - The pin name for the SCK signal. E.g. `"D0"`
- `mosi_pin` - **string** - The pin name for the MOSI signal. E.g. `"D1"`
- `miso_pin` - **string** - The pin name for the MISO signal. E.g. `"D2"`
- `cs_pin` - **string** - The pin name for the CS signal. E.g. `"D3"`
- `mode` - **integer** - The SPI mode. Can be `0`, `1`, `2`, or `3`
- `frequency` - **integer** - The SPI frequency in kHz. Can be `125`, `250`, `500`, `1000`, `2000`, `4000`, or `8000`
- `bit_order` - **string** - The bit order for transactions. Can be `"MSB_FIRST"` or `"LSB_FIRST"`
- `hold_cs` - **boolean** - If `true`, the CS pin remains held after the transaction completes. Useful for multi-step transactions
- `cs_active_high` - **boolean** - If `true`, the CS pin is set high during the transaction and low once completed
- `miso_pull` - **string** - The pull mode on the MISO pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **string** - The bytes read. Always of size `read_length`

**Example**

```lua
-- Read data from an SPI flash device
local data = device.spi.write_read("\x03\x00\x00\x00", 11)
print(data)
```

---

#### Write bytes to an SPI device

```lua
device.spi.write(data, { sclk_pin="C0", mosi_pin="C1", miso_pin="C2", cs_pin="C3", mode=0, frequency=4000, bit_order="MSB_FIRST", hold_cs=false, cs_active_high=false, miso_pull="NO_PULL" })
```

**Parameters**

- `data` - **string** - The data to write to the device

**Optional parameters**

- `sclk_pin` - **string** - The pin name for the SCK signal. E.g. `"D0"`
- `mosi_pin` - **string** - The pin name for the MOSI signal. E.g. `"D1"`
- `miso_pin` - **string** - The pin name for the MISO signal. E.g. `"D2"`
- `cs_pin` - **string** - The pin name for the CS signal. E.g. `"D3"`
- `mode` - **integer** - The SPI mode. Can be `0`, `1`, `2`, or `3`
- `frequency` - **integer** - The SPI frequency in kHz. Can be `125`, `250`, `500`, `1000`, `2000`, `4000`, or `8000`
- `bit_order` - **string** - The bit order for transactions. Can be `"MSB_FIRST"` or `"LSB_FIRST"`
- `hold_cs` - **boolean** - If `true`, the CS pin remains held after the transaction completes
- `cs_active_high` - **boolean** - If `true`, the CS pin is set high during the transaction and low once completed
- `miso_pull` - **string** - The pull mode on the MISO pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **nil**

**Example**

```lua
-- Wake up the flash with the 0xAB command
device.spi.write("\xAB")
```

---

#### Read bytes from an SPI device

```lua
device.spi.read(length, { sclk_pin="C0", mosi_pin="C1", miso_pin="C2", cs_pin="C3", mode=0, frequency=4000, bit_order="MSB_FIRST", hold_cs=false, cs_active_high=false, miso_pull="NO_PULL" })
```

**Parameters**

- `length` - **integer** - The number of bytes to read from the device

**Optional parameters**

- `sclk_pin` - **string** - The pin name for the SCK signal. E.g. `"D0"`
- `mosi_pin` - **string** - The pin name for the MOSI signal. E.g. `"D1"`
- `miso_pin` - **string** - The pin name for the MISO signal. E.g. `"D2"`
- `cs_pin` - **string** - The pin name for the CS signal. E.g. `"D3"`
- `mode` - **integer** - The SPI mode. Can be `0`, `1`, `2`, or `3`
- `frequency` - **integer** - The SPI frequency in kHz. Can be `125`, `250`, `500`, `1000`, `2000`, `4000`, or `8000`
- `bit_order` - **string** - The bit order for transactions. Can be `"MSB_FIRST"` or `"LSB_FIRST"`
- `hold_cs` - **boolean** - If `true`, the CS pin remains held after the transaction completes
- `cs_active_high` - **boolean** - If `true`, the CS pin is set high during the transaction and low once completed
- `miso_pull` - **string** - The pull mode on the MISO pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **string** - The bytes read. Always of size `length`

**Example**

```lua
-- Read 4 bytes from an SPI device
local data = device.spi.read(4)
print(data)
```

---

#### Transact bytes with an SPI device (write and read in parallel)

```lua
device.spi.transact(write_data, read_length, { sclk_pin="C0", mosi_pin="C1", miso_pin="C2", cs_pin="C3", mode=0, frequency=4000, bit_order="MSB_FIRST", hold_cs=false, cs_active_high=false, miso_pull="NO_PULL" })
```

**Parameters**

- `write_data` - **string** - The data to write to the device
- `read_length` - **integer** - The number of bytes to read from the device

**Optional parameters**

- `sclk_pin` - **string** - The pin name for the SCK signal. E.g. `"D0"`
- `mosi_pin` - **string** - The pin name for the MOSI signal. E.g. `"D1"`
- `miso_pin` - **string** - The pin name for the MISO signal. E.g. `"D2"`
- `cs_pin` - **string** - The pin name for the CS signal. E.g. `"D3"`
- `mode` - **integer** - The SPI mode. Can be `0`, `1`, `2`, or `3`
- `frequency` - **integer** - The SPI frequency in kHz. Can be `125`, `250`, `500`, `1000`, `2000`, `4000`, or `8000`
- `bit_order` - **string** - The bit order for transactions. Can be `"MSB_FIRST"` or `"LSB_FIRST"`
- `hold_cs` - **boolean** - If `true`, the CS pin remains held after the transaction completes
- `cs_active_high` - **boolean** - If `true`, the CS pin is set high during the transaction and low once completed
- `miso_pull` - **string** - The pull mode on the MISO pin. Can be `"PULL_UP"`, `"PULL_DOWN"`, or `"NO_PULL"`

**Returns**

- **string** - The bytes read. Always of size `read_length` as specified in the function call

**Example**

```lua
-- Write and read data simultaneously
local data = device.spi.transact("\x9F", 3)
print(data)
```

---

### UART communication

**Warning:** The UART functions are **not yet functional** in the current firmware release. Calls succeed silently but perform no UART operation. This section describes the planned interface.

#### Write UART data

```lua
device.uart.write(data, { baudrate=9600, tx_pin="B1", cts_pin=nil, parity=false, stop_bits=1 })
```

**Parameters**

- `data` - **string** - The data to send

**Optional parameters**

- `baudrate` - **integer** - The baudrate in bits-per-second. Can be `1200`, `2400`, `4800`, `9600`, `14400`, `19200`, `28800`, `31250`, `38400`, `56000`, `57600`, `76800`, `115200`, `230400`, `250000`, `460800`, `921600`, or `1000000`
- `tx_pin` - **string** - The pin name for the transmit signal. E.g. `"C1"`
- `cts_pin` - **string** - The pin name for the clear-to-send signal. E.g. `"C3"`. If `nil`, the signal isn't used
- `parity` - **boolean** - If `true`, enables the parity bit
- `stop_bits` - **integer** - The number of stop bits. Can be `1` or `2`

**Returns**

- **nil**

**Example**

```lua
-- Send UART data
device.uart.write("Hello there. This is some data\n", { baudrate=19200 })
```

---

#### Assign an event handler for UART data

```lua
device.uart.assign_read_event(terminator, handler, { baudrate=9600, rx_pin="B0", tx_pin="B1", rts_pin=nil, cts_pin=nil, parity=false, stop_bits=1 })
```

**Parameters**

- `terminator` - **string** - The character to wait for before triggering the event. If `nil`, the event triggers for every character received
- `handler` - **function** - The function to call when data is received. Called with one argument:
    - `data` - **string** - All buffered bytes since the last event or since the event was enabled

**Optional parameters**

- `baudrate` - **integer** - The baudrate in bits-per-second
- `rx_pin` - **string** - The pin name for the receive signal. E.g. `"C0"`
- `rts_pin` - **string** - The pin name for the ready-to-send signal. E.g. `"C2"`. If `nil`, the signal isn't used
- `parity` - **boolean** - If `true`, enables the parity bit

**Returns**

- **nil**

**Example**

```lua
-- Create a handler for receiving UART data
function my_receive_handler(data)
    print("Got a new line: "..data)
end

device.uart.assign_read_event("\n", my_receive_handler, { baudrate=19200 })
```

---

#### Disable a UART read event handler

```lua
device.uart.unassign_read_event(rx_pin)
```

**Parameters**

- `rx_pin` - **string** - The pin name of the receive signal. E.g. `"C0"`

**Returns**

- **nil**

**Example**

```lua
-- Disable the event and detach the pin from the handler if no longer needed
device.uart.unassign_read_event("B0")
```

---

## Networking libraries

### Networking (LTE)

#### Send data to Superstack

```lua
network.send_data{ data }
```

**Parameters**

- `data` - **table** - A table of key-value pairs. Converted to JSON when sent to Superstack. Use descriptive key names (e.g. `temperature_celsius = 43.5`) to help AI tools infer meaning

**Returns**

- **nil**

**Warning:** If the Device has no network connection, the data is **dropped** — it is not buffered by the firmware. If data must survive connectivity gaps, check `network.connected()` and buffer to a file using the [file storage](#file-storage) library until the connection returns.

**Note:** The table must not be empty, and top-level keys must be strings. A complete encoded message may be around **1KB** — keep individual payloads below **900 bytes** to be safe, and split larger data across multiple sends. The call is synchronous and can block for a few seconds on a poor connection. If the Deployment's data allowance has been exceeded, `send_data` and `print` become inactive until the allowance resets or code is re-deployed.

**Example**

```lua
-- A simple sensor value
my_sensor_value = 23.5

network.send_data{ temperature=my_sensor_value }

-- Network send can contain any arbitrary data
network.send_data{
    my_int = -42,
    my_float = 23.1,
    my_string = "my string",
    my_array = {1, 2, 3, 4},
    my_table = {
        my_other_int = 54,
        my_other_string = "another string"
    }
}
```

---

#### Check if the network is connected

```lua
network.connected()
```

**Returns**

- **boolean** - `true` if the LTE network is connected, `false` otherwise

**Example**

```lua
if network.connected() then
    print("Network is up")
end
```

---

#### Set low power mode

```lua
network.low_power_mode(enabled)
```

**Parameters**

- `enabled` - **boolean** - `true` to enable PSM (Power Saving Mode), `false` to disable it

**Returns**

- **nil**

**Warning:** Enabling PSM introduces up to **15 minutes of latency** for code updates from Superstack. To return to real-time updates, call `network.low_power_mode(false)` and wait up to 15 minutes for the modem to re-register.

**Example**

```lua
-- Enable low power mode when the network is not needed
network.low_power_mode(true)
```

---

### Location (GPS)

#### Enable GPS

```lua
location.enable({ accuracy="HIGH", power_saving="OFF", tracking_interval=1 })
```

**Optional parameters**

- `accuracy` - **string** - The accuracy of the fix. `"LOW"` requires three satellites, `"HIGH"` requires four satellites
- `power_saving` - **string** - The power saving level. Can be `"OFF"`, `"MEDIUM"`, or `"MAX"`. Higher power saving reduces accuracy and increases time to fix
- `tracking_interval` - **integer** - The period to poll for new location updates. `1` for continuous 1-second updates, or a value between `10` and `65535` seconds for slower updates to save power

**Returns**

- **nil**

**Warning:** `location.enable()` automatically activates PSM to allow the modem to share hardware with the GPS. This introduces up to **15 minutes of latency** for code updates from Superstack. To return to real-time updates, call `location.disable()` followed by `network.low_power_mode(false)`, then wait up to 15 minutes.

**Example**

```lua
-- Start GPS with default settings
location.enable{}

-- Start GPS with low accuracy to save power
location.enable{ accuracy="LOW", power_saving="MAX" }
```

---

#### Get the latest GPS data

```lua
location.get_latest()
```

**Returns**

- **table** - A table of key-value pairs:
    - `valid` - **boolean** - `true` if the GPS data is valid, or `false` otherwise
    - `latitude` - **number** - The current latitude
    - `longitude` - **number** - The current longitude
    - `altitude` - **number** - The current altitude
    - `accuracy` - **number** - The location and altitude accuracy
    - `speed` - **number** - The current speed
    - `speed_accuracy` - **number** - The speed accuracy
    - `satellites` - **table** - A table of key-value pairs:
        - `tracked` - **integer** - The number of satellites currently being tracked
        - `in_fix` - **integer** - The number of satellites currently being used for measurement
        - `unhealthy` - **integer** - The number of satellites that could not be used for measurement

**Example**

```lua
-- GPS must be enabled before getting a location fix
location.enable{ accuracy="HIGH", power_saving="OFF" }

-- Avoid sending logs or data while waiting for a fix — network
-- activity competes for the modem hardware and delays acquisition
device.sleep(60)

local l = location.get_latest()

print("valid: " .. tostring(l["valid"]))
print("latitude: " .. tostring(l["latitude"]))
print("longitude: " .. tostring(l["longitude"]))
print("altitude: " .. tostring(l["altitude"]))
print("accuracy: " .. tostring(l["accuracy"]))
print("speed: " .. tostring(l["speed"]))
print("speed_accuracy: " .. tostring(l["speed_accuracy"]))

print("satellites tracked: " .. tostring(l["satellites"]["tracked"]))
print("satellites in fix: " .. tostring(l["satellites"]["in_fix"]))
print("satellites unhealthy: " .. tostring(l["satellites"]["unhealthy"]))
```

---

#### Disable GPS

```lua
location.disable()
```

**Returns**

- **nil**

**Warning:** Disabling GPS alone does **not** restore real-time code updates. PSM remains active until `network.low_power_mode(false)` is called. After calling it, wait up to 15 minutes for the modem to re-register before Superstack can push updates in real time.

**Example**

```lua
-- Stop GPS and restore real-time connectivity
location.disable()
network.low_power_mode(false)
```

---

## System libraries

### Logging

#### Post log to Superstack

```lua
print(log)
```

**Parameters**

- `log` - **string** - String to print

**Returns**

- **nil**

**Example**

```lua
-- Simple print
print("hello world")

-- Print variables
local my_num = 4 + 3
print(my_num)

-- C printf style formatted prints
print(string.format("pi = %.4f", math.pi))
```

**Note:** Each log message is truncated to **1023 characters**. Prefer a single string argument: `print("a", "b")` produces **separate log entries** for each argument and separator, so use `string.format` or concatenation to combine values into one message. Logs stop being sent once the Deployment's data allowance is exceeded.

---

### Sleep

#### Sleep for a duration

```lua
device.sleep(time)
```

**Parameters**

- `time` - **number** - The duration to sleep in seconds. E.g. `1.5`

**Returns**

- **nil**

**Note:** Assigned event handlers continue to fire during sleep. See [assign an event handler](#assign-an-event-handler-for-a-pin-input-change).

**Example**

```lua
-- Sleep for 1.5 seconds
device.sleep(1.5)
```

---

### Power

#### Configure the battery charger

```lua
device.power.battery.set_charger_cv_cc(voltage, current)
```

**Parameters**

- `voltage` - **number** - The termination voltage. Can be `3.50`, `3.55`, `3.60`, `3.65`, `4.00`, `4.05`, `4.10`, `4.15`, `4.20`, `4.25`, `4.30`, `4.35`, `4.40`, or `4.45`
- `current` - **number** - The constant charge current in mA. Must be between `32` and `800` in steps of `2`

**Returns**

- **nil**

**Note:** This setting reverts to the firmware default (**3.50V** termination, **32mA** charge current) at reboot. Configure the charger near the top of your code so that it is reapplied whenever the script restarts.

**Example**

```lua
-- Configure the battery charger for a 4.2V 200mAh rated Li-Po cell
device.power.battery.set_charger_cv_cc(4.2, 200)
```

---

#### Get the battery voltage

```lua
device.power.battery.get_voltage()
```

**Returns**

- **number** - The voltage of the cell in volts

**Example**

```lua
local voltage = device.power.battery.get_voltage()
print("Battery voltage is "..tostring(voltage).."V")
```

---

#### Get the battery charging status

```lua
device.power.battery.get_charging_status()
```

**Returns**

- **string** - The charging status: `"charging"`, `"charged"`, or `"discharging"` if a battery is connected, or `"external_power"` if no battery is installed or the battery has a fault

**Example**

```lua
local status = device.power.battery.get_charging_status()

if status ~= "external_power" then
    print("Battery is "..status)
else
    print("Battery not connected. On external power")
end
```

---

#### Set the IO voltage for all ports

```lua
device.power.set_vout(voltage)
```

**Parameters**

- `voltage` - **number** - The IO voltage of `PORTA` - `PORTF`. Can be between `1.8` and `3.3` in steps of `0.1`, or `0` to switch the port power outputs off entirely

**Returns**

- **nil**

**Note:** At boot, the port rails default to **1.8V**. If a connected sensor requires a higher IO voltage, call this function before communicating with it.

**Example**

```lua
-- Set the voltage of Vout to 3.3V
device.power.set_vout(3.3)
```

---

### File storage

**Note:** The filesystem provides roughly **48kB** of usable space, **shared with the Device's code file**. Files survive code pushes and reboots, but are erased when the Device is un-paired from its Deployment.

#### Write data to a file

```lua
storage.write(filename, data)
```

**Parameters**

- `filename` - **string** - The name of the file
- `data` - **string** - The data to save to the file

**Returns**

- **nil**

**Example**

```lua
-- Create a file and write data to it
storage.write("my_file.txt", "Hello world")
```

---

#### Append data to a file

```lua
storage.append(filename, data)
```

**Parameters**

- `filename` - **string** - The name of the file
- `data` - **string** - The data to append to the file

**Returns**

- **nil**

**Example**

```lua
-- Append more data to the file
storage.append("my_file.txt", "\nThis is another line of text")
storage.append("my_file.txt", "\nAnd this is a final line of text")
```

---

#### Read data from a file

```lua
storage.read(filename, { line=1, length=nil, offset=0 })
```

**Parameters**

- `filename` - **string** - The name of the file

**Optional parameters**

- `line` - **integer** - The line index to return. `1` is the first line, `2` the second, etc. Negative values index from the end: `-1` is the last line, `-2` the second to last, etc. Cannot be `0`, and cannot be combined with `length` or `offset`
- `length` - **integer** - The number of bytes to read. Cannot be used with `line`. If longer than the file, a shorter result is returned
- `offset` - **integer** - When `length` is specified, read from this byte offset within the file

**Returns**

- **string** - The contents read

**Example**

```lua
-- Read the first line of the file
print(storage.read("my_file.txt"))

-- Print the last line from the file
print(storage.read("my_file.txt", { line=-1 }))
```

**Note:** Reading a file which does not exist raises an error. Use `pcall`, or check with `storage.list()` first.

---

#### Delete a file

```lua
storage.delete(filename)
```

**Parameters**

- `filename` - **string** - The name of the file

**Returns**

- **boolean** - `true` if the file was found and deleted, `false` otherwise

**Example**

```lua
-- Delete the file
storage.delete("my_file.txt")
```

---

#### List all files

```lua
storage.list()
```

**Returns**

- **table** - A table of tables:
    - **table** - A table of key-value pairs:
        - `name` - **string** - The name of the file
        - `size` - **integer** - The size of the file in bytes

**Example**

```lua
-- List all files on the device
local files = storage.list()
for i, file in ipairs(files) do
    print(file.name .. " - " .. file.size .. " bytes")
end
```

---

### Timekeeping

#### Get the current Unix timestamp

```lua
time.get_unix_time()
```

**Returns**

- **integer** - The current Unix timestamp (i.e the number of non-leap milliseconds that have elapsed since 00:00:00 UTC on 1 January 1970), or if the time is not yet known, returns the uptime of the device in milliseconds

**Example**

```lua
-- Repeat something for 30 seconds
local t = time.get_unix_time()

while t + 30000 > time.get_unix_time() do
    print("waiting")
    device.sleep(5)
end
```

Note: the returned value is in **milliseconds**, so 30 seconds is `30000`

---

#### Get the current time and date

```lua
time.get_time_date({ unix_epoch, timezone })
```

**Optional parameters**

- `unix_epoch` - **number** - A Unix timestamp to convert to a time and date
- `timezone` - **string** - The timezone offset. E.g. `"+02:00"` or `"-07:30"`

**Returns**

- **table** - A table of key-value pairs:
    - `year` - **integer** - The current year
    - `month` - **integer** - The current month
    - `day` - **integer** - The current day
    - `yearday` - **integer** - The current day of the year
    - `weekday` - **integer** - The current day of the week since Sunday
    - `hour` - **integer** - The current hour
    - `minute` - **integer** - The current minute
    - `second` - **integer** - The current second

**Example**

```lua
-- Print the current time and date
local now = time.get_time_date()

print(string.format("The current time is: %02d:%02d", now.hour, now.minute))
print(string.format("The current date is: %d/%d/%d", now.year, now.month, now.day))
```

---

### Device information

#### Hardware version constant

```lua
device.HARDWARE_VERSION
```

**Returns**

- **string** - Always `"s2-module"`

**Example**

```lua
print(device.HARDWARE_VERSION)
```

---

#### Firmware version constant

```lua
device.FIRMWARE_VERSION
```

**Returns**

- **string** - A string representing the current firmware version. E.g. `"0.1.0+0"`

**Example**

```lua
print(device.FIRMWARE_VERSION)
```
