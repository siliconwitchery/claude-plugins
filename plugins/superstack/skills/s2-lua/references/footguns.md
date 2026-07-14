# S2 Lua — Footguns, Quirks & Recovery Recipes

Verified behaviors that commonly produce broken-looking code or "bricked-looking"
devices. Every item here is confirmed against the official docs or hardware
specs; a final section lists things that are *not* documented, with the safe
conservative assumption to code against.

## Contents

- [Time is in milliseconds; sleep is in seconds](#time-is-in-milliseconds-sleep-is-in-seconds)
- [The PSM / GPS trap](#the-psm--gps-trap)
- [GPS acquisition vs network activity](#gps-acquisition-vs-network-activity)
- [Everything you send costs data allowance](#everything-you-send-costs-data-allowance)
- [Error handling differs per bus](#error-handling-differs-per-bus)
- [There is no downlink channel](#there-is-no-downlink-channel)
- [Store-and-forward pattern](#store-and-forward-pattern)
- [Battery charger voltage list has a gap](#battery-charger-voltage-list-has-a-gap)
- [Ports boot at 1.8 V; VOUT applies to all ports at once](#ports-boot-at-18-v-vout-applies-to-all-ports-at-once)
- [JTAG erase permanently destroys the module's identity](#jtag-erase-permanently-destroys-the-modules-identity)
- [LED states worth knowing when debugging](#led-states-worth-knowing-when-debugging)
- [Confirmed runtime behavior](#confirmed-runtime-behavior)
- [Known firmware issues (v2.0.2)](#known-firmware-issues-v202)

## Time is in milliseconds; sleep is in seconds

The two time-related units are different and this is the most common bug:

- `time.get_unix_time()` returns **milliseconds** since the Unix epoch — and
  before the first network time sync it returns **device uptime in
  milliseconds** instead, not wall-clock time.
- `device.sleep(t)` takes **seconds** (fractions allowed, e.g. `1.5`).

```lua
-- WRONG: waits 30 milliseconds, not 30 seconds
local t = time.get_unix_time()
while t + 30 > time.get_unix_time() do ... end

-- RIGHT
local t = time.get_unix_time()
while t + 30000 > time.get_unix_time() do ... end
```

(The official docs' own example for `time.get_unix_time()` currently contains
the wrong version above — do not copy it.)

**Wait-for-valid-time idiom** — before timestamping logged data, make sure the
clock is synced, not uptime. A freshly booted device that hasn't synced returns
values near zero (uptime), so a plausibility threshold works:

```lua
-- Unix ms for 2024-01-01; anything below this is uptime, not wall time
local TIME_VALID_THRESHOLD = 1704067200000

local function wait_for_valid_time()
    while time.get_unix_time() < TIME_VALID_THRESHOLD do
        device.sleep(1)
    end
end
```

## The PSM / GPS trap

Symptom: *"my device ignores code updates / seems bricked after I enabled GPS."*

Cause chain:

1. `location.enable{}` **silently activates PSM** (LTE Power Saving Mode) so the
   modem can share hardware with the GPS receiver. `network.low_power_mode(true)`
   activates PSM explicitly.
2. Under PSM, code pushes from Superstack take up to **15 minutes** to reach the
   device (they arrive at the next modem wake), instead of seconds.
3. `location.disable()` alone does **not** deactivate PSM.

Full recovery recipe (restore real-time code updates):

```lua
location.disable()
network.low_power_mode(false)
-- then wait up to 15 minutes for the modem to re-register.
```

Note the recovery code itself is delivered as a code push — so it may take up to
15 minutes to land on a PSM-active device. The device is not bricked; it is
sleeping. Never suggest re-flashing firmware for this (see JTAG section).

Preventive guidance for generated code: if the application needs responsive
remote development, avoid `location.enable` / `low_power_mode(true)` during the
iteration phase; add them once the code is stable and field-deployed.

## GPS acquisition vs network activity

While waiting for a GPS fix, avoid `print()` and `network.send_data` — network
activity competes for the shared modem hardware and delays acquisition. Enable
GPS, sleep, then read `location.get_latest()` and check its `valid` flag before
using coordinates. Time to first fix ranges 1.3 s to 30.5 s with sky view.

## Everything you send costs data allowance

Counted against the deployment's monthly data allowance:

- every `print()` log
- every `network.send_data{}` payload
- **every code push — the entire code file is retransmitted to every target
  device.** Pushing a 50 kB file to 20 devices costs ~1 MB.

Not counted: automatic firmware updates, and platform telemetry (power, location,
usage) viewed in Superstack.

Consequences for generated code:

- no `print()` in tight loops; remove debug prints before fleet deployment
- batch readings and send one table instead of many small sends
- keep JSON keys descriptive but not verbose (keys are payload too — see
  agent-tuning guidance in the superstack-api skill: descriptive keys feed the
  AI agent's schema inference)
- reference scale: one temperature value every 15 minutes ≈ 0.5 MB/month, and
  the Free tier includes 1 MB/month

## Error handling differs per bus

| API | Failure surface |
|---|---|
| `device.i2c.read/write/write_read` | returns a table with a `success` boolean — **always check it** |
| `device.spi.*`, `device.uart.*`, `device.analog.*`, `device.digital.*` | no success flag — invalid arguments raise errors |
| `device.i2c.scan` | returns nil; results appear in the logs |

Wrap fragile sections (sensor init, bus transactions with possibly-absent
devices) in `pcall` so one failed transaction doesn't kill the whole script:

```lua
local ok, err = pcall(function()
    local r = device.i2c.write_read(0x76, "\xD0", 1, { port = "PORTA" })
    if not r.success then
        print("sensor not responding")
    end
end)
if not ok then
    print("i2c error: " .. tostring(err))
end
```

## There is no downlink channel

There is no MQTT, no `network.receive()`, no webhooks to the device, no remote
function calls, and no per-device config API. Do not invent one. The two
sanctioned patterns:

1. **Config as constants + re-push** — put tunables at the top of the file as
   named constants; changing a threshold means editing and re-pushing the code
   (remember the data cost × fleet size).
2. **Stop/start as a remote kill switch** — the REST API can stop and start a
   device's code remotely (see the superstack-api skill).

## Store-and-forward pattern

**Confirmed: `network.send_data` while offline drops the data** — there is no
firmware-side buffering. For field deployments, anything that must survive a
connectivity gap needs to be gated on `network.connected()` and buffered to
flash:

```lua
local BUFFER_FILE = "backlog.txt"

local function record(json_ready_table)
    if network.connected() then
        -- drain any backlog first
        local backlog = storage.read(BUFFER_FILE)
        if backlog and #backlog > 0 then
            for line in backlog:gmatch("[^\n]+") do
                network.send_data{ raw = line }
            end
            storage.delete(BUFFER_FILE)
        end
        network.send_data(json_ready_table)
    else
        -- store a compact representation for later
        storage.append(BUFFER_FILE, encode_line(json_ready_table) .. "\n")
    end
end
```

(Adapt `encode_line` per application; keep buffered lines compact — flash
storage is limited.)

## Battery charger voltage list has a gap

`device.power.battery.set_charger_cv_cc(voltage, current)` accepts **only** these
termination voltages:

```
3.50 3.55 3.60 3.65 4.00 4.05 4.10 4.15 4.20 4.25 4.30 4.35 4.40 4.45
```

There are no valid values between 3.65 and 4.00 — e.g. `3.7`, `3.8`, `3.85` are
invalid despite being common LiFePO4/NiMH-ish numbers. Current: 32–800 mA in
2 mA steps. Standard single-cell Li-Po → `set_charger_cv_cc(4.2, C/1)` where the
current matches the cell's rated charge current (e.g. 200 for a 200 mAh cell at
1C).

## Ports boot at 1.8 V; VOUT applies to all ports at once

**At boot the port rails are live at 1.8 V** (confirmed by Silicon Witchery).
This is a trap: a 3.3 V sensor on an unconfigured port doesn't fail cleanly —
it may half-work, with marginal I2C signaling and garbage readings. Always call
`device.power.set_vout(3.3)` in setup before talking to 3.3 V sensors.

`device.power.set_vout(voltage)` sets the IO voltage for **all** ports PORTA–F
together (1.8–3.3 V, 0.1 V steps). You cannot run PORTA at 1.8 V and PORTD at
3.3 V. Mixed-voltage sensor sets need external level shifting or the 5 V VSYS
rail plus regulators.

## JTAG erase permanently destroys the module's identity

The S2 can technically be erased over Tag-Connect/J-Link and loaded with custom
firmware — but this **permanently erases the SoftSIM, the data plan, and the
Superstack license**. The module can never be used with Superstack again.

Never suggest re-flashing, factory reset, or "erase and reprogram" as a
troubleshooting step. There is no user-facing factory reset. For a device that
seems unresponsive to code pushes, see the PSM trap above; for pairing issues,
un-pair/re-pair from Superstack (requires access to the owning deployment).

## LED states worth knowing when debugging

| Observation | Meaning |
|---|---|
| Network LED strobing rapidly | **Firmware update in progress (~5 min). Do not power off** — power loss restarts the update. May go dark near the end; wait it out. |
| Network LED off | Connected & idle — this is normal operation, not a fault |
| Network LED slow blink | Searching for LTE — check antenna clearance, band coverage for the country |
| Network LED solid | Network found but not paired to a deployment |
| Power LED short blinks | On battery, no external power |

## Confirmed runtime behavior

Verified against the firmware source (v2.0.2, July 2026):

| Behavior | Fact |
|---|---|
| Lua version | **5.5** (`_VERSION` reports "Lua 5.5"). Opened libraries: base, coroutine, table, string, math, utf8. **No `io`, `os`, or `debug`** |
| `require` | A minimal `require("name")` **exists but is undocumented**: it loads `name.lua` from device storage and **re-executes the module on every call** (no `package.loaded` caching). Default to single-file programs; if used, guard against repeated execution |
| `network.send_data` while offline | **Data is dropped silently** — no firmware buffering, no error return. Use the store-and-forward pattern above for anything that must survive connectivity gaps |
| `send_data` limits | Whole encoded message ≈ 1 KB — **keep user payloads under ~900 bytes** and split larger data. Errors on empty tables and non-string top-level keys (array-style `send_data{1,2,3}` fails). Synchronous: can block up to ~5 s on a poor connection |
| Data-allowance blocking | Once the deployment's data allowance is exceeded, `send_data` **and** `print` become silently inert until the allowance resets or the server sends a code action. A device that "stopped logging" may just be over allowance |
| `print` | Truncated at **1023 chars** per message. Multi-argument `print("a", "b")` sends a **separate log message per argument and separator** (3 network posts) — always build one string with `string.format` or `..` |
| VOUT at boot | **Live at 1.8 V** — see the section above; set 3.3 V before using 3.3 V sensors. `set_vout(0)` switches the port power off entirely |
| Event handlers during `device.sleep()` | **Fire live** — they interrupt the sleep, run immediately, and the sleep then resumes. Keep handlers short; shared state they touch can change across any `sleep()` call. Note: any other digital/analog operation on a pin silently cancels that pin's event handler |
| Runtime error | Script **halts**; `codeState` becomes `error` (visible via REST); the Lua error message and line number appear in the Logs tab. No auto-restart — fix and re-push. Wrap risky sections in `pcall` to keep running |
| Busy loop (no `sleep`) | Does **not** harm the system — the Lua thread runs at lower priority than networking/OTA, and code pushes interrupt Lua via an instruction hook. The cost is power draw, so still always sleep in the main loop |
| Charger configuration | `set_charger_cv_cc` does **not** persist across reboots — the firmware default (**3.50 V / 32 mA**, minimum-safe) is programmed at every boot. Configure the charger in setup; code restarts from the top on every boot/push, so setup naturally reapplies it |
| Lua heap | **64 KiB pool** (slightly less usable). Avoid accumulating large tables or long strings; stream to `storage`; process files line-by-line (`storage.read` with `line=`) |
| Storage capacity | ≈ **48 KiB usable**, **shared with the pushed code file** (same filesystem). No file-count limit. Files survive code pushes and reboots; **everything is erased on un-pair**. Big scripts shrink the space left for data files |
| I2C/SPI transfers | Max **8191 bytes** per transfer. SPI pin options (`sclk/mosi/miso/cs`) must be given all-or-none |
| GPS + PSM timing | PSM is requested as TAU 900 s / active 30 s — hence "up to 15 minutes". The network may grant different values |
| Globals across a code push | In-memory state does not survive a push — code restarts from the top. `storage` files persist |

## Known firmware issues (v2.0.2)

Real defects confirmed in the current firmware — useful when a customer's
symptom matches. (Tracked for fixing; recheck on newer firmware versions.)

| Symptom | Cause |
|---|---|
| Rail measures **0.1 V lower** than set for `set_vout` values 1.9, 2.3, 2.4, 2.8, 2.9, **3.3** (→ 3.2 V) | Float truncation in the voltage→register conversion. Workaround: none from Lua; most 3.3 V sensors tolerate 3.2 V |
| `set_charger_cv_cc(4.10, …)` or `(4.35, …)` raises "voltage must be…" despite being documented values | Same truncation class. Workaround: use 4.15 or 4.20 (check cell specs) |
| UART calls do nothing (no error, no data) | `device.uart.*` are unimplemented stubs in current firmware — do not generate UART code |
| `spi.write_read` behaves wrong (writes on default pins C0–C3 regardless of options) | Shim bug: options are ignored for the write phase. Workaround: use `device.spi.transact` directly, or `spi.write` + `spi.read` |
| `storage.read` with negative `line` returns `""` for the first line of a file, or when the file ends with `\n` | Backward-scan edge cases. Workaround: track line counts and use positive indices, or avoid trailing newlines in buffer files |
| `send_data` "succeeds" but nothing arrives, for payloads in the ~960–1074 encoded-byte range | Encode buffer larger than transport buffer; error not propagated. Stay under ~900 bytes |
| `device.analog.get_input("D0", {})` errors with "number expected" | Passing an options table without `acquisition_time` fails to default. Workaround: omit the table entirely, or always include `acquisition_time` |
| `battery` percentage shows 0 in Superstack device telemetry | Unit-mix bug in the status uplink calculation (Lua `get_voltage()` is unaffected) |
| `get_time_date().yearday` is 0-based (Jan 1 → 0) | Missing +1; add one if you need conventional day-of-year |
| `device.FIRMWARE_VERSION` returns e.g. `"2.0.2"` without the documented `+tweak` suffix | Uses the non-extended version string |
