# Open questions & pre-release tasks

## Firmware questions — ANSWERED (2026-07-14, confirmed by Raj)

Facts now encoded in `s2-lua/references/footguns.md` → "Confirmed runtime
behavior":

- [x] `network.send_data` while offline → **data is dropped** (no buffering)
- [x] Event handlers during `device.sleep()` → **fire live**, sleep resumes
- [x] VOUT at boot → **live at 1.8 V** (3.3 V sensors half-work until `set_vout`)
- [x] Runtime error → script halts, `codeState: error`, message + line in Logs
- [x] Watchdog/busy loop → system stays healthy (Lua runs at lower priority;
      connectivity/OTA/pushes unaffected); cost is power only
- [x] Lua version → **5.4**
- [x] Charger config → does **not** persist across reboots (reverts to default)
- [x] Lua heap → tight, **under 64 KB**

All remaining unknowns were answered by firmware source verification
(2026-07-14, see `~/projects/s2-firmware/TODO.md` for the full findings):

- [x] `send_data`: ~1 KB encoded message; keep payloads under ~900 bytes
- [x] Log messages: truncated at 1023 chars; multi-arg `print` fragments
- [x] Charger default: 3.50 V / 32 mA, programmed at every boot
- [x] Storage: ~48 KiB usable littlefs, shared with the code file; survives
      pushes/reboots; erased on un-pair; no file-count limit
- [x] Lua: **5.5** (not 5.4); heap = 64 KiB pool; no `debug` library; an
      undocumented `require()` exists (no caching)

Pending Raj's decisions in the firmware TODO (affects docs + skill once
decided): UART implement-vs-remove, `storage.read` default semantics,
`require` official or not, script-size limit vs partition size.

## Docs repo fixes — DONE (uncommitted in ~/projects/docs, review & push)

- [x] `pages/superstack/lua.md` — fixed `time.get_unix_time()` example
      (`t + 30` → `t + 30000` + ms note); patch removed from
      `scripts/generate-references.py`
- [x] `pages/superstack/lua.md` — fixed the broken 3-arg `device.i2c.write`
      example in Coding principles (line 45) to match the documented signature
- [x] `pages/superstack/lua.md` — fixed two dead anchors in Standard libraries
- [x] `pages/superstack/lua.md` — documented confirmed behaviors as callouts:
      send_data offline drop, VOUT 1.8 V boot default, charger non-persistence,
      handlers firing during sleep
- [x] `pages/s2-module.md` — added the textual pin/port table (was images-only)
- [ ] Commit + push the docs repo changes (Jekyll site redeploys)

## Before first release

- [x] Answer firmware questions; update `footguns.md`
- [ ] Run the eval suite: prompts in README "Try it" section + PSM recovery,
      with and without the skill, on at least two model tiers
- [ ] Test `superstack.py` against a live deployment (read-only key)
- [ ] Test install: `claude --plugin-dir plugins/superstack`, then
      `/plugin marketplace add siliconwitchery/claude-plugins` from a clean repo
- [x] `claude plugin validate .` clean
- [ ] Add `SYNC_PR_TOKEN` repo secret (PAT) so sync-docs PRs trigger CI
- [ ] Commit this repo, tag v0.1.0, attach skill zips for claude.ai users
- [ ] Drop `.claude/settings.json` with `extraKnownMarketplaces` into
      `s2-lua-examples` repo
- [ ] List on skills.sh; submit to anthropics/claude-plugins-community
