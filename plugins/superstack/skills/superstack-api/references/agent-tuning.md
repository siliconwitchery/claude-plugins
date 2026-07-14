# Getting good answers from the Superstack AI agent

The Superstack Agent answers natural language questions about deployment data. Answer
quality depends almost entirely on the quality of the metadata you give it — device
names, groups, roles, and data key names. This reference explains why, and how to
write that metadata well.

## How the agent works: the three-step pipeline

Every query runs as an orchestrated multi-step process. The LLM never sees raw data
rows — it only sees metadata, data structure, and its own generated logic.

1. **Filter Tool** — Examines deployment metadata (device names, groups, locations,
   and sensor types) and the JSON data structure to determine exactly which
   rows of data are relevant to the query. If no time range is given, it assumes a
   reasonable recent default and excludes stale readings. Output is a precise filter
   specification — no raw data is shared with the AI provider.
2. **Analysis Tool** — Takes the Filter result and compiles deterministic, executable
   code tailored to the query (means, daily grouping, unit conversion, outlier
   handling, temporal integration, etc.). The generated algorithm runs in
   Superstack's secure runtime against the filtered data. The LLM only writes the
   code; it never processes the actual sensor values.
3. **Explain Tool** — Turns the computed result into a clear, domain-specific answer
   using the Agent Role, device metadata, and chat history, along with the reasoning
   from the previous steps.

**Why this matters for you:** because the model reasons only over metadata and
schema, the agent can only be as good as the metadata it sees. A query fails in the
Filter step when the model can't tell which devices/fields are relevant (ambiguous
names), and in the Analysis step when it can't tell what the numbers mean (missing
units). A reasoning breakdown for each response is available for debugging failed
queries.

## The six context sources

| Source | What it tells the agent | Writing guidance |
|---|---|---|
| **Agent Role** | The overall goal of the agent | State the domain, the deployment's purpose, and conventions ("You are an expert gardener monitoring a commercial greenhouse; temperatures are in Celsius; alert thresholds are..."). Max 2000 characters via the API. |
| **Device Name** | What the specific device is monitoring | Name the thing measured, not the hardware: `Tomatoes`, `Barn roof array` — not `S2-0042`, `dev3`. Max 50 characters. |
| **Device Group** | How devices are grouped together | Use groupings users will query by: `greenhouse`, `outside`. "Average temperature in my greenhouse" only works if a `greenhouse` group exists. Max 50 characters. |
| **Device Role** | Specifics about the device, its sensors, and analysis-relevant details | Complete, domain-specific sentences: sensor models, units, placement, expected ranges, reporting interval. Max 2000 characters. |
| **Data schema** | Inferred from the JSON keys and value types of `network.send_data()` payloads | Key names ARE the schema — see next section. |
| **Previous Chat Context** | Conversational context for follow-up questions | Include prior messages via the `messages` array when querying over the API (see below). |

General rule from the docs: use explicit details wherever possible. Avoid ambiguous
technical names or acronyms; include complete, domain-specific information.

**Good Device Role:**
> "I monitor Roma tomato plants in greenhouse bay 2. I report soil moisture as a
> percentage, air temperature in Celsius, and light in lux, every 15 minutes. Ideal
> soil moisture is 40-60%."

**Bad Device Role:**
> "SHT31 + cap sensor on GPIO4, FW v2"

## Data key naming in Lua becomes the schema

The keys you pass to `network.send_data()` are extracted (with value types) as the
data schema the Filter and Analysis tools rely on. Put units and full words in key
names so the Analysis tool converts and aggregates correctly.

**Good:**

```lua
network.send_data({
    air_temperature_celsius = 23.5,
    soil_moisture_percent = 45.2,
    light_lux = 850,
})
```

**Bad:**

```lua
network.send_data({
    t = 23.5,   -- temperature? time? what unit?
    sm = 45.2,  -- ambiguous acronym
    l = 850,
})
```

With the bad keys, a query like "how many watt hours were generated in May?" is
exactly the kind that fails in the Analysis step — the model cannot know whether a
value is instantaneous power or accumulated energy. `power_output_watts` makes the
required `sum(power * interval_hours)` integration unambiguous.

## Using the REST agent endpoints

Base URL pattern: `https://super.siliconwitchery.com/api/{deploymentId}/...` with
your API key in the `X-Api-Key` header. Each agent has a Role, access to some or all
device groups, and an optional list of WhatsApp users.

### Get and set roles programmatically

- `GET /api/{deploymentId}/agents` — list agents (requires **read agents**
  permission). Returns `id`, `name`, `role`, `groups` (empty = all groups), `users`,
  and `usage` (tokens used this billing period).
- `GET /api/{deploymentId}/agent/{agentId}/info` — retrieve one agent's `name`,
  `role`, `groups`, `users`, `created`, `accessed`.
- `POST /api/{deploymentId}/agents` — create an agent (requires **edit agents**).
  Body: `name` (max 50 chars), `role` (max 2000 chars), `groups`, `users`. The
  deployment must contain at least one device first.
- `PUT /api/{deploymentId}/agent/{agentId}/info` — update the Agent Role. Same body
  as create; all fields are replaced with the values given, and listed WhatsApp
  users are re-sent the introduction message.
- Device Roles are set per device: `PUT /api/{deploymentId}/device/{deviceId}/info`
  with `name` (required, max 50), `group` (required, max 50), `bookmarked`, and
  `role` (max 2000 chars). All fields are replaced; omitted optional fields are
  cleared — so always send the full object.

### Querying an agent

```
POST /api/{deploymentId}/agent/{agentId}/query
```

Requires the **query agents** permission. Request body:

```jsonc
{
    "messages": [
        {
            "role": "user",  // "user" or "assistant"
            "content": "What is the average temperature in the greenhouse?"
        }
    ]
}
```

For follow-up questions, include the previous `user` and `assistant` messages before
the new question — this is how the chat-history context source works over the API.

Response:

```jsonc
{
    "response": "The average temperature in the greenhouse is currently 23.5°C...",
    "answer": "23.5",       // Raw computed answer
    "reasoning": {          // Internal reasoning (for debugging)
        "filter": "Filtered to greenhouse devices from the last 6 hours",
        "analysis": "Calculated mean temperature from all greenhouse sensors"
    },
    "usage": 1350           // Tokens consumed by this query
}
```

Use `answer` for programmatic consumption, `response` for humans, and `reasoning` to
debug bad answers: a wrong `filter` line means fix names/groups/roles; a wrong
`analysis` line means fix key names and units.

### Metering and allowance

AI allowance is a token pool measured per deployment, set by the subscription plan,
and reset each billing period.

- `GET /api/{deploymentId}/agents/usage?days=` — total usage across all agents
  (requires **read agents**). Returns `allowance`, `used`, `remaining`,
  `billingDay`, and a time-bucketed `usage` map (hourly intervals under 14 days,
  otherwise daily). When `days` is given, totals cover the last `days` days and
  `billingDay` is `0`.
- `GET /api/{deploymentId}/agent/{agentId}/usage?days=` — per-agent time-bucketed
  `usage` map.

Every query response includes its token cost in `usage`; WhatsApp queries count
toward the same allowance as API queries. Once the deployment's allowance for the
billing period is used up, queries return **402 Payment Required** until the next
billing period.
