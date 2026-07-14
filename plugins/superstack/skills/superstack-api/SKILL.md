---
name: superstack-api
description: >-
  Integrates with the Silicon Witchery Superstack IoT platform REST API:
  retrieving device data, logs, and telemetry, pushing and controlling Lua code
  on S2 Module fleets, managing devices and deployments, and chatting with the
  Superstack AI agent. Also covers tuning agent roles and data schemas for
  better AI answers. Use when the user mentions the Superstack API, exporting
  or querying S2 device data, fleet code deployment, Superstack dashboards or
  automations, or Superstack API keys.
license: Apache-2.0
compatibility: >-
  Making live API calls requires network access and a Superstack API key
  (Claude Code / Agent SDK). In sandboxed environments without network, use
  this skill to generate curl commands or client code for the user to run.
metadata:
  vendor: siliconwitchery
  docs: https://docs.siliconwitchery.com/pages/superstack/api
---

# Superstack REST API integration

## Basics

- Base URL: `https://super.siliconwitchery.com/api/{deploymentId}/...`
- The **Deployment ID** is on the Superstack Settings tab.
- Auth: `X-Api-Key` header. Keys are created per-deployment on the Settings
  tab with **granular permissions** (e.g. read-only data). All deployments are
  private; only the signed-out **Demo Deployments** allow keyless reads.
- Success with no body → `{"ok": "OK"}`. Failures → HTTP status +
  `{"error": "<description>"}`.
- Full endpoint reference: [references/rest-api.md](references/rest-api.md)

**Key hygiene (non-negotiable):** never inline an API key in code, notebooks,
or committed files. Read it from an environment variable
(`SUPERSTACK_API_KEY`), and recommend minimal-permission keys (read-only for
dashboards). Treat any key that has appeared in a chat, log, or commit as
compromised — the user should delete it in Settings and create a new one.

## The filter pattern (the #1 stumbling block)

`GET .../logs` and `GET .../data` take a `filters` query parameter whose value
is a **JSON-encoded string** — it must be URL-encoded. The canonical pattern:

```sh
curl -G "https://super.siliconwitchery.com/api/$DEPLOYMENT_ID/data" \
    --data-urlencode 'filters={"devices": ["Greenhouse 1"], "startTime": "2026-07-01T00:00:00Z"}' \
    -H "X-Api-Key: $SUPERSTACK_API_KEY"
```

(`curl -G --data-urlencode` handles the URL encoding; in Python use
`params={"filters": json.dumps(f)}` with `requests`, or the bundled script.)

Filter rules (same for logs and data):

- `devices` / `groups` filter by **name** (mutable — renames break saved
  queries), `bookmarked: true` filters bookmarked devices.
- Time window: `startTime`/`endTime` (ISO 8601; defaults: last hour → now),
  **or** cursor pagination: `id` (a reference entry ID) + `count` (negative =
  older than id, positive = newer; max 1000).
- Time range and `id`/`count` **cannot be combined**. No filters at all →
  latest 100 entries.
- Responses include `newerAvailable`/`olderAvailable` booleans — paginate by
  taking the last `id` from the page and repeating with `count`.

## Fleet code deployment gotchas

- `PUT /device/{deviceId}/code` replaces a device's Lua (server accepts up to
  100,000 chars, but the device filesystem is only ~48 KiB **shared with the
  device's `storage` data files** — keep scripts well under ~40 KB, and
  smaller if the app buffers data to storage). `POST /code/push` fans code out
  to many targets — **addressed by device/group name**, not ID, and it
  overwrites whatever code those devices had.
- Every push retransmits the **entire file to every target device** and counts
  against the deployment's data allowance. Warn before large-fleet pushes.
- `codeState` on a device can be `running`, `stopped`, or `error` — after a
  push, verify it; on `error`, read the Logs for the Lua error message.
- Stop/start endpoints are the only remote kill switch (there is no downlink
  config channel to devices).
- `POST /device` (pairing) **blocks up to 60 s** waiting for the physical
  button press on the module — use a long HTTP timeout there.
- Destructive calls (`DELETE` device/log/data) require `{"confirm": true}` in
  the body, and un-pairing a device **permanently deletes its data and logs**.
  Always confirm with the user before generating/running deletes.

## No webhooks — poll

The API has no webhooks or push notifications. Integrations poll. Pattern:
remember the newest seen `id`, poll `.../data` with
`filters={"id": <last>, "count": 1000}`, process, repeat. The public dashboard
demo (github.com/siliconwitchery/superstack-dashboard-demos) polls once per
second; for data-frequency-matched polling, poll at the device send interval.

## Bundled helper script

[scripts/superstack.py](scripts/superstack.py) is a zero-dependency (stdlib
Python 3) CLI that handles auth headers, filter URL-encoding, pagination, and
the code-size limit:

```sh
export SUPERSTACK_API_KEY=...   # never passed as an argument
python3 scripts/superstack.py data --deployment $ID --devices "Greenhouse 1" --since 7d
python3 scripts/superstack.py code-push --deployment $ID --group greenhouse --file main.lua
```

Prefer the script when network access is available; otherwise emit the
equivalent `curl -G --data-urlencode` commands for the user.

## The Superstack AI agents

A deployment can have **multiple AI agents**, each with a Role, scoped to
specific device groups (empty = all), and optionally exposed to named users
over WhatsApp. Endpoints: `/agents` CRUD, `POST /agent/{agentId}/query`, and
per-agent + deployment-wide usage. Answer quality is determined by context the
customer controls — how to write Device Roles, Agent Roles, and data key
names: [references/agent-tuning.md](references/agent-tuning.md).

## Validation checklist

Before delivering Superstack API code:

- [ ] Endpoint + method exist in rest-api.md — no invented endpoints/webhooks
- [ ] API key from env var; minimal permissions suggested
- [ ] `filters` JSON is URL-encoded (curl `-G --data-urlencode` / params dict)
- [ ] Pagination uses `id`+`count` cursors; respects the 1000 cap
- [ ] Device/group name mutability caveat mentioned for saved automations
- [ ] Destructive calls gated on explicit user confirmation
- [ ] Fleet pushes note the data-allowance cost
