# Phase 6 — Governance controls test matrix

One row per control the demo exercises: **prerequisite/license**, the exact
**demo action** (with a visible before → after), the **expected result**, **where
to observe** it, and the **pillar** it belongs to.

Pillars: **① Telemetry** · **② Threat protection** · **③ Governance**. Pillar ①
(observability) is the prerequisite for ② — Defender detects from the Agent 365
observability data the agent emits.

Agent identifiers to substitute (from `a365.generated.config.json`, git-ignored):
`agenticAppId` (the agent identity / `AgentId` in hunting), `agentBlueprintId`,
`agentRegistrationId`, `tenantId`.

---

## ③ Governance — Microsoft Entra Agent ID

| Control | Prereq / license | Demo action (before → after) | Expected result | Where to observe |
| --- | --- | --- | --- | --- |
| Agent identity exists | Agent 365 enabled | Show the agent's Entra identity + blueprint + sponsor; decode the observability token | `azp`/`sub` in the token = the per-agent identity (`agenticAppId`), not the blueprint | Entra admin center (entra.microsoft.com) → **Agent ID / Agent identities**; decode token at jwt.ms |
| Conditional Access for the agent identity | Conditional Access Admin (or GA); Workload Identities Premium (verify) | Create a CA policy targeting the agent's **workload identity** (block from a named location / require compliant network) → re-run the token service | S2S token request is **denied**; the exporter logs the failure (no HTTP 200) | Entra → **Protection → Conditional Access**; **Sign-in logs → Service principal sign-ins** for the agent identity |
| Lifecycle — disable / de-sponsor | Identity Admin | Disable the agent identity (or remove the sponsor) → next token acquisition | Token acquisition **fails**; exporter stops exporting | Entra sign-in logs; note where **Access reviews / Lifecycle Workflows** would attach |
| Identity gate (admin consent) | Application Administrator (prereq) + GA (consent) | Show the blueprint's application permissions and the consent grant | Permissions consented by a Global Admin (e.g. `access_agent_as_user`, `Agent365.Observability.OtelWrite`) | Entra admin center → **Agent identities → blueprint → Permissions**; see [GOVERNANCE_GATES.md](GOVERNANCE_GATES.md) |

> These are tenant-state changes — pause and hand the portal steps to the operator.
> Exact Entra "Agent ID" UI paths for agent-targeted CA are evolving; verify
> against the current Microsoft Entra Agent ID docs before the demo.

## ③ Governance — Microsoft 365 admin center

| Control | Prereq / license | Demo action (before → after) | Expected result | Where to observe |
| --- | --- | --- | --- | --- |
| Registry visibility | Agent 365 enabled | Open the agent in the registry | Agent listed with **owner, status, platform**; **Activity** page opens | admin.microsoft.com → **Agents → All agents** (Registry) → select `gemini-secagent` |
| Distribution gate (admin approval queue) | none | Open **Agents → All agents → Requests** | **No request** for this agent (S2S agent was registered, not published) | admin.microsoft.com → **Agents → All agents → Requests** — see [GOVERNANCE_GATES.md](GOVERNANCE_GATES.md) <!-- TODO: if Phase 4 implements `a365 publish`, flip this row to "Pending review expected" --> |
| Block / Unblock | Agent management permission | **Block** the agent → next agent call; then **Unblock** | Blocked → call fails; Unblocked → recovers; action is audited | Agents → All agents → select → **Block** / **Unblock** → Save |
| Apply a security template (via agent management rule) | Agent management permission | Agents → **Settings → Agent management rules → Add rule → Apply template**; define criteria; run on the agent | The template's policies apply (the rule "evaluates agents in the registry that **have an agent identity**" — ours qualifies; not blueprints/AI teammates) | Agents → **Settings → Agent management rules**; policy templates: `/microsoft-agent-365/admin/policy-template` |
| Allowed agent types | Agent management permission | Toggle Microsoft / your-org / external-publisher categories | Agents of a disabled type don't appear/install for users | Agents → **Settings → Allowed agent types** |
| User access | Agent management permission | Set All / No / Specific users/groups | Restricts who can use agents | Agents → **Settings → User access** |
| Tag the agent | Agent management permission | Agents → **Settings → Tags → Add**; apply the tag to the agent | Tag appears on the agent; usable as a filter/criteria | Agents → **Settings → Tags** |
| Work IQ permission revoke/re-grant | **Deferred** — needs OBO | N/A on this S2S branch | — | Deferred to the `ai-teammate` branch (see `docs/DEFERRED.md`) |

## ① Telemetry (observability)

| Control | Prereq / license | Demo action | Expected result | Where to observe |
| --- | --- | --- | --- | --- |
| Spans on the Activity page | ≥1 tenant user with **E7 / Agent 365** license | Send one prompt (`make telemetry-check` or `adk web`) | `invoke_agent → inference → tool` spans appear | admin.microsoft.com → Agents → `gemini-secagent` → **Activity** |
| Same activity in hunting | Security Admin | Run `hunting/agent_activity_24h.kql` | Tool/inference rows for the agent | Defender → **Investigation & response → Hunting → Advanced hunting** (`CloudAppEvents`) |

## ② Threat protection — Microsoft Defender

Prereq for all: **Security for AI agents** enabled (Defender portal → System →
Settings) + the Microsoft 365 app connector; Security Administrator; the E7/Agent
365 license gate (same as ①). Near-real-time **detection** applies to this
SDK-integrated agent; inline **runtime blocking** is limited (Prompt Shields for
Foundry / Agent Builder; local agents need Defender for Endpoint) — don't
overclaim.

### Posture / inventory

| Control | Demo action | Expected result | Where to observe |
| --- | --- | --- | --- |
| Inventory + posture | Open the agent after activity ingests | Agent row with **Risk level, Risk indicators, Recommendations, Active alerts**; details → tools, identity, MCP servers | Defender → **Assets → AI agents → Agents** tab → select `gemini-secagent` → **Open Agent page** |

### Detections — one row per corpus class

`make attack-run`, then correlate by the **session id** the runner prints.
Defender's documented detection classes are: jailbreak, indirect prompt injection
(XPIA), malicious content propagation, secret/credential leakage, evasion, LLM
reconnaissance, suspicious user/IP access.

| Corpus case (class) | Expected detection | Notes |
| --- | --- | --- |
| `benign-control` (benign) | **No alert expected** | Proves normal use isn't flagged |
| `jailbreak-direct` / `-roleplay` (jailbreak) | Jailbreak-attempt alert | — |
| `xpia-indirect-injection` (indirect_prompt_injection) | Indirect prompt injection (XPIA) alert | Fixture-planted instructions |
| `credential-leak` (credential_leak) | Secret / credential leakage alert | Fake API key is the bait |
| `data-exfil-bulk` (data_exfiltration) | Secret/credential-leakage or exfil-framed alert | Verify exact title in tenant |
| `recon-system-prompt` / `-tools-model` (llm_recon) | LLM reconnaissance alert | — |
| `evasion-base64` / `-homoglyph` (evasion) | Evasion-technique alert | Obfuscated credential-leak |
| `tool-abuse-enumeration` (tool_abuse) | May surface as anomalous execution | No 1:1 named class — verify; may correlate rather than alert |
| `known-trigger` (operator-supplied) | Per `A365_KNOWN_TRIGGER_CLASS` | Payload never logged (sha256 only) |

Observe in: Defender → **Incidents & alerts** (correlated incident graph; open an
alert for the **prompt evidence** snippet), and the saved
[hunting/](../hunting) queries (`AlertInfo`+`AlertEvidence`, `BehaviorInfo`).

## Deferred rows

| Control | Why deferred | Reference |
| --- | --- | --- |
| Registry sync vs SDK registration (side by side) | Needs a Google Cloud / Vertex AI project | `docs/DEFERRED.md` |
| Purview DLP / DSPM for AI | Out of scope (Appendix A only) | plan Appendix A |

---

**Legend:** *before → after* means show the audience the state, apply the
control, then show it changed. Every row that changes tenant state is operator-run
in the portal — the lab code doesn't perform governance actions.
