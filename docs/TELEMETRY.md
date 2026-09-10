# Telemetry contract (Phase 3)

How this Gemini/ADK agent emits Agent 365 observability, what spans it produces,
and how to verify them. Auth mode is **S2S** (see
[PHASE2_REGISTRATION.md](PHASE2_REGISTRATION.md)).

## What Phase 3 adds

The agent stays Gemini-native. Observability is layered around it via the
unified **`microsoft-opentelemetry`** distro (no legacy `microsoft-agents-a365-*`
packages):

- **Bootstrap before ADK import** — [security_agent/__init__.py](../security_agent/__init__.py)
  calls `init_observability()` before importing `google.adk`, so the distro's
  GenAI auto-instrumentation patches the model libraries.
- **S2S FMI token service** — a daemon thread acquires the Observability API
  token via the 3-hop FMI chain and refreshes it every 50 min; the exporter
  reads it from an in-memory cache per export.
- **`InvokeAgentScope` per turn** — ADK `before_agent_callback` /
  `after_agent_callback` open/close the scope and set baggage (tenant + agent
  id). Inference and tool spans are auto-instrumented and nest inside it.

## Files

| File | Role |
| --- | --- |
| [observability/config.py](../observability/config.py) | Resolves `AGENT365_*` config from the CLI-stamped root `.env` (accepts the CLI's own names too). |
| [observability/bootstrap.py](../observability/bootstrap.py) | Calls `use_microsoft_opentelemetry(...)` (S2S flags) + starts the token thread. |
| [observability/observability_token_service.py](../observability/observability_token_service.py) | 3-hop FMI token chain (Blueprint → Agent Identity → Observability API). |
| [observability/token_cache.py](../observability/token_cache.py) | Thread-safe token cache the exporter reads from. |
| [observability/obs_context.py](../observability/obs_context.py) | `AgentDetails` + `CallerDetails` (sponsor identity for S2S). |
| [observability/adk_instrumentation.py](../observability/adk_instrumentation.py) | ADK callbacks that wrap each turn in `InvokeAgentScope`. |
| [scripts/telemetry_check.py](../scripts/telemetry_check.py) | The Phase 3 gate (`make telemetry-check`). |

## The span tree

One turn that calls a tool produces (verified by `make telemetry-check`):

```
invocation                                  (ADK root)
└─ invoke_agent SecurityResearchAssistant   ← InvokeAgentScope (before/after_agent)
   └─ invoke_agent gemini-secagent Identity
      ├─ generate_content / call_llm         ← inference (auto-instrumented)
      └─ execute_tool get_customer_record    ← tool (auto-instrumented)
```

- **Required for the Activity page:** a valid `invoke_agent` span at the root of
  the run. Without it, spans stay queryable in Defender advanced hunting but
  never surface on the Activity page / Defender / Purview.
- Key attributes: `gen_ai.*` (model, operation, tool name), plus tenant + agent
  id carried as **baggage** (`microsoft.tenant.id`, `gen_ai.agent.id`). Missing
  identity → spans filtered as "0 identity groups".

## Where it lands

| Surface | Table / view |
| --- | --- |
| M365 admin center | the agent's **Activity** page |
| Defender advanced hunting — activity | `CloudAppEvents` (tool executions, inference) |
| Defender advanced hunting — inventory | `AgentsInfo` |

## Configuration (root `.env`)

The CLI stamps most of these; the sponsor block was added in Phase 3. The config
loader accepts either the `AGENT365_*` names or the CLI's own names.

```dotenv
# Stamped by `a365 setup all` (CLI names shown; AGENT365_* aliases also accepted)
AGENT365OBSERVABILITY__TENANTID=...
AGENT365OBSERVABILITY__AGENTID=...
AGENT365OBSERVABILITY__AGENTBLUEPRINTID=...
AGENT365OBSERVABILITY__CLIENTID=...
AGENT365OBSERVABILITY__CLIENTSECRET=...      # secret — git-ignored
ENABLE_A365_OBSERVABILITY_EXPORTER=true

# Added Phase 3 — S2S has no signed-in user, so CallerDetails uses the sponsor
AGENT365_USE_MANAGED_IDENTITY=false          # true only on Azure (MSI); false for local dev
AGENT365_SPONSOR_USER_ID=<sponsor object id>
AGENT365_SPONSOR_USER_EMAIL=<sponsor@tenant>
AGENT365_SPONSOR_USER_NAME=<display name>
```

- **`a365_use_s2s_endpoint=True`** (set in code) posts to `/observabilityService/`
  (S2S) not `/observability/` (OBO) — wrong endpoint → 401.
- Local dev uses **client-secret** FMI (managed identity off); on Azure set
  `AGENT365_USE_MANAGED_IDENTITY=true`.

## Verify

```zsh
make telemetry-check     # runs one tool-calling turn and asserts the contract
```

Checks: (a) S2S token acquired, (b) `InvokeAgent → inference → tool` tree,
(c) tenant + agent id on spans. **Client-side only** — full surfacing on the
Activity page also needs a tenant user with an **E7 / Microsoft Agent 365**
license (otherwise telemetry is dropped silently even on HTTP 200).

## Known benign noise

- `Failed to set up A365 OpenAI Agents instrumentation … No module named 'agents'`
  — the distro probes for the OpenAI Agents SDK, which we don't use. Google ADK
  is instrumented regardless.
- MSAL `DeprecationWarning` about a static `client_assertion` — from the S2S
  scaffold; the token still acquires and refreshes every 50 min.
