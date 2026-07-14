# S2 Module — Pin & Port Reference

Machine-readable pin map for the Silicon Witchery S2 Module. Transcribed from the
official pinout diagrams (docs.siliconwitchery.com/pages/s2-module). Pin names are
the exact strings accepted by the Lua API (e.g. `"A0"`, `"C3"`).

## Contents

- [Valid pin names](#valid-pin-names)
- [Port map](#port-map)
- [Analog-capable pins](#analog-capable-pins)
- [I2C port shortcut and Qwiic pin order](#i2c-port-shortcut-and-qwiic-pin-order)
- [Power rails](#power-rails)
- [Bottom pads](#bottom-pads)

## Valid pin names

The complete set of IO pin names on the S2 Module. Any other pin string is invalid
and will fail.

```
A0 A1  B0 B1  C0 C1 C2 C3 C4  D0 D1 D2 D3 D4  E0 E1  F0 F1
```

18 IO pins total. All pins support digital input/output. Only the 8 pins marked
below support analog input.

## Port map

Six IO ports. PORTA/B/E/F are 4-pin connectors; PORTC/D are 7-pin connectors.
Physical pin 1 is always GND, pin 2 is always the port's VOUT rail.

| Port  | Connector | Power rail | IO pins (connector pin №) | Analog-capable |
|-------|-----------|------------|---------------------------|----------------|
| PORTA | 4-pin     | VOUT1      | A0 (3), A1 (4)            | none           |
| PORTB | 4-pin     | VOUT1      | B0 (3), B1 (4)            | none           |
| PORTC | 7-pin     | VOUT1      | C0 (3), C1 (4), C2 (5), C3 (6), C4 (7) | C2, C3, C4 |
| PORTD | 7-pin     | VOUT2      | D0 (3), D1 (4), D2 (5), D3 (6), D4 (7) | D0, D1, D2, D3, D4 |
| PORTE | 4-pin     | VOUT2      | E0 (3), E1 (4)            | none           |
| PORTF | 4-pin     | VOUT2      | F0 (3), F1 (4)            | none           |

There are also two power connectors (not IO ports):

| Connector    | Pins                          |
|--------------|-------------------------------|
| Power Port   | 1: VSYS, 2: VIN, 3: GND       |
| Battery Port | 1: VBATT, 2: GND              |

## Analog-capable pins

`device.analog.get_input()` and `device.analog.get_differential_input()` only work
on these 8 pins:

```
C2 C3 C4 D0 D1 D2 D3 D4
```

Before generating analog code, verify the chosen pin is in this list. `A0`, `B1`,
`E0`, etc. are digital-only — analog reads on them are invalid.

## I2C port shortcut and Qwiic pin order

The `port` option in `device.i2c.*` calls is valid **only** for `"PORTA"`,
`"PORTB"`, `"PORTE"`, and `"PORTF"` (the 4-pin ports). It assumes the
Stemma QT / Qwiic pin order:

| Connector pin | Qwiic signal | Pin name (PORTA example) |
|---------------|--------------|--------------------------|
| 1             | GND          | —                        |
| 2             | 3.3 V        | — (VOUT1/VOUT2)          |
| 3             | SDA          | A0                       |
| 4             | SCL          | A1                       |

So with `port="PORTA"`: SDA = A0, SCL = A1. Same pattern on B/E/F (SDA = x0,
SCL = x1).

For I2C on PORTC or PORTD (or non-Qwiic wiring), pass explicit `scl_pin` and
`sda_pin` instead — `port` and explicit pins are mutually exclusive.

Note: Qwiic devices expect 3.3 V. Call `device.power.set_vout(3.3)` if the IO
voltage may have been configured lower.

## Power rails

| Rail  | Feeds                       | Max current            | Voltage                      |
|-------|-----------------------------|------------------------|------------------------------|
| VOUT1 | PORTA, PORTB, PORTC (pin 2) | 100 mA across all three ports | Off, or 1.8–3.3 V in 0.1 V steps |
| VOUT2 | PORTD, PORTE, PORTF (pin 2) | 100 mA across all three ports | Off, or 1.8–3.3 V in 0.1 V steps |
| VSYS  | Power Port pin 1            | up to 1 A (shared with radio, charging, VOUT rails) | fixed 5 V |

Important constraints:

- **The rails boot live at 1.8 V.** A 3.3 V sensor on an unconfigured port may
  half-work with marginal signaling — call `device.power.set_vout(3.3)` in
  setup before first sensor contact.
- **VOUT1 and VOUT2 always track the same voltage** — they derive from one
  internal source. The Lua API sets one voltage for all ports:
  `device.power.set_vout(voltage)` applies to PORTA–PORTF together
  (`set_vout(0)` switches both rails off). There is no per-rail Lua control.
- A 5 V sensor cannot be powered from an IO port. Use VSYS (5 V, Power Port
  pin 1) and remember its 1 A budget is shared with the modem and charger.
- IO logic level follows the VOUT setting. Absolute max on any IO pin is
  VOUT + 0.3 V.

## Bottom pads

The bottom of the module exposes the same signals as the physical connectors as
gold pads for pogo-pin mounting on a carrier PCB. Pad assignments mirror the port
map above (same pin names, same numbering). See the mechanical drawing on the
datasheet page for the landing pattern.
