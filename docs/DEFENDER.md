# Phase 5 — Threat protection with Microsoft Defender

Microsoft Defender detects jailbreak / prompt-injection / credential-leak /
tool-abuse behavior on this agent from the **Agent 365 observability data** we
emit in Phase 3. **Telemetry is the prerequisite** — no spans, no detections.

> Defender watches the telemetry, not the agent directly. The spans reach it via
> the A365 service → `sentinel` sink (see
> [how-agent-telemetry-works.md](how-agent-telemetry-works.md)).

## 0. One-time tenant enablement (manual — do before running attacks)

These are tenant-state changes; do them yourself in the portal:

1. **Defender portal** → https://security.microsoft.com → **System** →
   **Settings** → **Security for AI agents** → **enable security for AI agents**
   and the **Microsoft 365 app connector** that ingests Agent 365 observability
   data.
2. Confirm **prompt evidence collection** is on (default) so alerts include the
   triggering prompt snippet.
3. Record the expected **ingestion delay** — run the corpus a while before you
   need to see results (near-real-time, but not instant).

Prereqs: **Security Administrator** role; Defender XDR licensing that covers
Security for AI agents; a tenant user with an **E7 / Agent 365** license (or
telemetry is dropped silently — same gate as Phase 3).

## 1. Run the adversarial corpus

```zsh
make attack-run       # full corpus (+ operator known trigger if configured)
make attack-known     # ONLY the operator-supplied known trigger
make attack-show      # print the known trigger + copy to clipboard (pbcopy)
```

The corpus ([attacks/corpus.yaml](../attacks/corpus.yaml)) has one case per
detection class, each **synthetic and safe** (no real secrets, no external
endpoints, no destructive tools):

| Case id | Defender class | What it does |
| --- | --- | --- |
| `benign-control` | benign | Normal question — **no alert expected**. |
| `jailbreak-direct` / `-roleplay` | jailbreak | Instruction-override / role-play. |
| `xpia-indirect-injection` | indirect_prompt_injection | `fetch_url` reads a fixture with hidden exfil instructions (XPIA). |
| `credential-leak` | credential_leak | Coax the agent to print the fake API key. |
| `recon-system-prompt` / `-tools-model` | llm_recon | Probe system prompt / tools / model. |
| `tool-abuse-enumeration` | tool_abuse | Bulk `get_customer_record` calls. |
| `data-exfil-bulk` | data_exfiltration | Dump all synthetic PII. |
| `evasion-base64` / `-homoglyph` | evasion | Obfuscated instruction. |
| `known-trigger` | operator-supplied | The operator's own trigger (payload never logged). |

`run.py` records each case's **response + timestamp + session id** to
`attacks/runs/<ts>.jsonl` (git-ignored) and prints a summary. The
**known-trigger session id** is surfaced at the end — paste it into the hunting
queries.

> Gemini free tier is 20 requests/day/model; the full corpus is ~15–20 calls, so
> it can exhaust quota. Errored cases are recorded and the run continues — re-run
> later or use a model with remaining quota.

## 2. What to look at afterwards

### Defender portal
- **Assets → AI agents → `gemini-secagent`** — risk level, risk indicators,
  recommendations, and the tools / MCP servers tab.
- **Incidents & alerts** — the correlated incident graph; open an alert to see
  the **prompt evidence** snippet.

### Advanced hunting (Investigation & response → Hunting)
Run the saved queries in [hunting/](../hunting) — fill `AgentId` from
`a365.generated.config.json` (field `agenticAppId`):

| Query | Table | Shows |
| --- | --- | --- |
| [agent_inventory.kql](../hunting/agent_inventory.kql) | `AgentsInfo` | the agent's inventory row |
| [agent_activity_24h.kql](../hunting/agent_activity_24h.kql) | `CloudAppEvents` | tool/inference activity (last 24h) |
| [agent_alerts.kql](../hunting/agent_alerts.kql) | `AlertInfo` + `AlertEvidence` | alerts + evidence (incl. prompt snippet) |
| [agent_behavior.kql](../hunting/agent_behavior.kql) | `BehaviorInfo` | real-time behavior signals, if any |

Filter alerts to a specific test case by the **session id** printed by the runner.

## 3. Detection vs. runtime blocking (don't overclaim)

- **Near-real-time detection** (alerts from observability data) **does** apply to
  this SDK-integrated third-party agent — that's what the corpus exercises.
- **Runtime blocking / inline protection** (stopping a prompt mid-flight) is, at
  the time of writing, primarily available for **Copilot Studio / Foundry**
  agents, not SDK-integrated third-party agents. Verify against the current
  [Defender AI agent detection & protection docs](https://learn.microsoft.com/defender-xdr/security-for-ai/ai-agent-detection-protection)
  before claiming inline blocking in a demo.

So for this lab: expect **alerts, incidents, posture, and hunting** — treat
runtime blocking as out of scope unless the docs say otherwise for your tenant.
