# Silicon Witchery Claude Plugins

Agent Skills and Claude Code plugins for the [S2 Module](https://docs.siliconwitchery.com/pages/s2-module)
and [Superstack](https://docs.siliconwitchery.com/pages/superstack) — teaches AI
assistants to write S2 Lua code and integrate with the Superstack API.

## What's inside

One plugin, `superstack`, containing two skills:

| Skill            | What it teaches Claude |
|------------------|------------------------|
| `s2-lua`         | Writing on-device Lua for the S2 Module: pins and ports, I2C/SPI/UART/analog, GPS, power and battery, file storage, sending data, and writing I2C sensor drivers from datasheets — including the quirks and footguns that aren't obvious from the docs. |
| `superstack-api` | The Superstack REST API: querying data/logs/telemetry, fleet code deployment, pagination and filter encoding, API key hygiene, and tuning the built-in AI agent. Includes a zero-dependency Python helper script. |

## Install

### Claude Code (recommended)

```
/plugin marketplace add siliconwitchery/claude-plugins
/plugin install superstack@siliconwitchery
```

Skills trigger automatically when you ask about S2 or Superstack topics. You can
also invoke them explicitly: `/superstack:s2-lua`, `/superstack:superstack-api`.

### Any agent that supports Agent Skills

The skills follow the open [Agent Skills](https://agentskills.io) format. Copy
the skill folders into your agent's skills directory, e.g. for Claude Code
without plugins:

```sh
git clone https://github.com/siliconwitchery/claude-plugins
cp -r claude-plugins/plugins/superstack/skills/* ~/.claude/skills/
```

### claude.ai

Download the skill zips from the latest
[release](https://github.com/siliconwitchery/claude-plugins/releases) and upload
them under **Settings → Capabilities → Skills**.

## Try it

With the plugin installed, ask Claude things like:

- *"Read temperature from a BMP280 on PORTA of my S2 every 10 minutes and send it to Superstack — don't lose data when the connection drops."*
- *"My S2 stopped taking code updates after I enabled GPS. Is it bricked?"*
- *"Export last week's data for the greenhouse group to CSV."*

## Repository layout

```
.claude-plugin/marketplace.json     Marketplace catalog (add via /plugin marketplace add)
plugins/superstack/                 The plugin
  .claude-plugin/plugin.json
  skills/s2-lua/                    On-device Lua skill
  skills/superstack-api/            REST API skill
scripts/                            CI tooling (reference generation from the docs repo)
```

Reference files under `references/` marked `GENERATED` are produced from the
[siliconwitchery/docs](https://github.com/siliconwitchery/docs) repo by
`scripts/generate-references.py` — edit the docs, not the generated files.
Hand-written files (`pinout.md`, `footguns.md`, `SKILL.md`) are maintained here.

## License

[Apache-2.0](LICENSE)
