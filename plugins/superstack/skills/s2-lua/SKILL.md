---
name: s2-lua
description: >-
  Writes and reviews Lua code for the Silicon Witchery S2 Module (nRF9151-based
  LTE Cat-M1 + GNSS IoT module) running on the Superstack platform. Covers
  digital/analog IO on PORTA-PORTF, I2C, SPI, UART, GPS/location, power and
  battery management, file storage, network.send_data, sleep/timing, and writing
  I2C sensor drivers from datasheets. Use when the user mentions the S2 Module,
  Superstack device code or Lua, wiring sensors to an S2, or IoT code for
  Silicon Witchery hardware.
license: Apache-2.0
compatibility: >-
  No local toolchain required — S2 code is deployed over-the-air via the
  Superstack web editor or REST API. This skill needs no network access itself.
metadata:
  vendor: siliconwitchery
  docs: https://docs.siliconwitchery.com
  examples: https://github.com/siliconwitchery/s2-lua-examples
---

# Writing Lua for the S2 Module

## What the S2 runtime is

The S2 Module runs user code in a sandboxed Lua 5.5 environment on the device,
managed entirely by the Superstack cloud platform. Facts that shape all code:

- **One Lua file per device.** The device filesystem is ~48 KiB shared between
  the code file and `storage` data files — keep scripts compact. Write
  single-file programs: a minimal undocumented `require()` exists (loads
  `name.lua` from storage, re-executing it on **every** call) but should not
  be relied on.
- Standard libraries available: basic, `math`, `string`, `table`, `utf8`,
  `coroutine`. **Not available: `io`, `os`, or `debug`** — use `storage.*`
  for files and `time.*` / `device.*` instead.
- Code is pushed over LTE and **restarts from the top** on every save/push and
  on reboot. In-memory state does not survive a push; `storage` files do.
- There is no local debugger. `print()` goes to the Superstack Logs tab;
  iteration is edit → save → observe logs (takes effect within seconds, unless
  PSM is active — see footguns).
- Hardware APIs follow one convention: required positional arguments first,
  then one optional table of named options — `f(a, b, { opt=1 })` or the
  table-only sugar `f{ opt=1 }`.

## Canonical program shape

Every S2 program follows this shape (full version: `assets/program-template.lua`):

```lua
-- 1. Config constants (change values here, then re-push)
local SEND_INTERVAL_S = 600

-- 2. One-time setup
device.power.set_vout(3.3)          -- ports boot at 1.8 V; raise before sensor use

-- 3. Optional event handlers
-- device.digital.assign_input_event("A0", function(pin, state) ... end)

-- 4. Main loop — always ends with device.sleep()
while true do
    -- read sensors, send data
    device.sleep(SEND_INTERVAL_S)
end
```

Never write a busy loop without `device.sleep()` — it wastes power. (It won't
break the system: Lua runs at lower priority, so connectivity, OTA updates,
and code pushes keep working even through a stuck loop.)

## Critical rules

These are the highest-frequency failure modes. Full explanations and recovery
recipes: [references/footguns.md](references/footguns.md).

1. **Pins**: only use pin names from
   [references/pinout.md](references/pinout.md). 18 pins exist
   (`A0-A1, B0-B1, C0-C4, D0-D4, E0-E1, F0-F1`). Analog input works **only** on
   `C2-C4` and `D0-D4`. Do not invent pins.
2. **Units**: `time.get_unix_time()` returns **milliseconds** (and uptime until
   first network time sync — use the wait-for-valid-time idiom before
   timestamping). `device.sleep()` takes **seconds**.
3. **I2C `port` shortcut** is only valid for `PORTA/B/E/F` (Qwiic pin order:
   pin 3 = SDA, pin 4 = SCL). On PORTC/D pass explicit `scl_pin`/`sda_pin`.
   `port` and explicit pins are mutually exclusive.
4. **PSM trap**: `location.enable{}` (GPS) silently enables LTE Power Saving
   Mode → code pushes stall up to **15 minutes**. Recovery requires
   `location.disable()` **and** `network.low_power_mode(false)`, then waiting.
   A device in this state is not bricked — never suggest re-flashing (JTAG
   erase permanently destroys the SIM and Superstack license).
5. **Data is billable and bounded**: every `print()`, every
   `network.send_data`, and every code push (full file × every target device)
   counts against the deployment's data allowance. Batch sends; strip debug
   prints before fleet deployment. Keep each `send_data` payload under ~900
   bytes; logs truncate at 1023 chars; **always print one string** —
   `print("a", b)` sends a separate network message per argument. Over
   allowance, sends and prints go silently inert.
6. **Error models differ**: I2C calls return `{ success = boolean, ... }` —
   always check it. SPI/UART/analog/digital return raw values with no flag —
   wrap risky sections in `pcall`.
7. **No downlink**: there is no MQTT, `network.receive`, webhook-to-device, or
   remote config. Config = constants at the top of the file + re-push. Remote
   control = REST stop/start (see the superstack-api skill).
8. **Offline is not handled for you**: assume `network.send_data` while
   disconnected loses data. Gate on `network.connected()` and buffer to
   `storage` (store-and-forward pattern in footguns.md).
9. **Power**: ports boot **live at 1.8 V** — a 3.3 V sensor on an unconfigured
   port half-works (marginal I2C, garbage readings) rather than failing
   cleanly. Call `device.power.set_vout(3.3)` in setup. It sets **all** ports
   at once (1.8–3.3 V); 100 mA total per rail (VOUT1: ports A/B/C, VOUT2:
   ports D/E/F). 5 V sensors go on VSYS. Charger termination voltages are a
   fixed list with **no valid values between 3.65 and 4.00 V**, and charger
   config reverts to firmware defaults on reboot — set it in setup.
10. **AI-friendly data keys**: `network.send_data{ temperature_celsius = 23.5 }`
    — descriptive snake_case keys with units. The Superstack AI agent infers
    the data schema from these keys; cryptic keys degrade every future
    natural-language query on the deployment.
11. **Memory is tight**: the Lua heap is under 64 KB. Don't accumulate large
    tables or long strings — stream to `storage` and process files
    line-by-line (`storage.read` with `line=`).

## Where to look things up

- Exact function signatures, parameters, return shapes for every Lua API →
  [references/lua-api.md](references/lua-api.md)
- Pin names, analog capability, port/rail map, Qwiic order →
  [references/pinout.md](references/pinout.md)
- Writing a driver for a new I2C/SPI sensor from its datasheet (register
  conventions, endianness, sign handling, CRC) →
  [references/sensor-drivers.md](references/sensor-drivers.md)
- Complete worked programs (sensor loop, GPS tracker, store-and-forward) →
  [references/examples.md](references/examples.md)
- Quirks, traps, recovery recipes, confirmed runtime facts, and **known
  firmware issues in the current release** (check here when a symptom looks
  like a hardware fault) → [references/footguns.md](references/footguns.md)

## Workflow for sensor-driver requests

When the user names a sensor part number (e.g. "read a BMP280 on PORTA"):

1. Check [references/sensor-drivers.md](references/sensor-drivers.md) and the
   examples repo (github.com/siliconwitchery/s2-lua-examples) for an existing
   driver for that part or family.
2. If none exists, follow the raw-register methodology in sensor-drivers.md:
   identify the I2C address and key registers from the datasheet, use
   `device.i2c.write_read` for register reads, handle endianness and
   two's-complement explicitly, and check `success` on every transaction.
3. State the sensor's supply voltage and confirm the wiring (which port, VOUT
   setting) before the code.

## Validation checklist

Before delivering S2 Lua code, verify:

- [ ] Every pin name exists and analog pins are analog-capable (pinout.md)
- [ ] Every API call matches a signature in lua-api.md — no invented functions
- [ ] Units: sleep in seconds, unix time in ms, voltages in the valid lists
- [ ] Every I2C result checks `.success`; fragile sections wrapped in `pcall`
- [ ] Main loop contains `device.sleep()`; no busy-waiting
- [ ] `set_vout` called in setup if any port-powered sensor is used
- [ ] Data-allowance impact stated for the chosen send/log frequency
- [ ] If GPS or PSM is used: the 15-minute code-push latency is called out
