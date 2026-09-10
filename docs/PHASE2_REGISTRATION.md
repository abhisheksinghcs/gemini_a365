# Phase 2 — Register in Agent 365 (identity)

**Status:** Prepared, not executed. This document is the reviewed plan for
registering the baseline Gemini agent in Microsoft Agent 365. Registration
changes tenant state (creates an Entra blueprint + agent identity and grants
permissions), so it is run interactively with a pause at each consent step — see
[Execution](#execution).

> Sources: [Agent 365 SDK overview](https://learn.microsoft.com/microsoft-agent-365/developer/agent-365-sdk),
> [Get started](https://learn.microsoft.com/microsoft-agent-365/developer/get-started),
> [agent365-skills README](https://github.com/microsoft/agent365-skills).

## What Phase 2 delivers

The Agent 365 SDK **does not build or host the agent** — our Gemini/ADK agent
still owns the model, framework, and host. Registration adds an **Entra-backed
identity** so the agent appears in the Agent 365 catalog and can later carry
telemetry (Phase 3) and governed tooling.

Onboarding is four stages; Phase 2 covers stage 1:

| Stage | Phase | What happens |
| --- | --- | --- |
| 1. **Register** | **Phase 2** | Create the agent identity **blueprint** + **agent identity** in Entra; grant permissions. Agent appears in the catalog. |
| 2. Extend | Phase 3–4 | Add observability, Work IQ tooling. |
| 3. Validate | Phase 3+ | `a365-code-validator`; confirm identity + telemetry. |
| 4. Operate | Phase 6 | Govern and audit via Agent 365 controls. |

## Our path: Standard agent, S2S

Our agent is a **Standard agent** (the skills call this *"Agent (Non AI
Teammate)"*) — it has **no** Agentic User, UPN, or mailbox. It authenticates via
an **Entra Agent Blueprint + Agent Identity**.

Auth mode is **S2S (Service Principal, no user token)**: the Gemini runtime has
no inbound Microsoft 365 user token, so the agent runs independently with service
principal credentials. This is the correct mode for a background/service agent.

### S2S vs OBO — why it matters

| | **S2S** (our choice) | **OBO** (On-Behalf-Of) |
| --- | --- | --- |
| Token subject | The agent's own service principal | A signed-in user |
| Requires a user in the loop | No | Yes |
| Access scope | The agent identity's granted permissions | Bounded by the user's permissions **and** their consent |
| Observability (Phase 3) | ✅ Supported | ✅ Supported |
| Work IQ tooling (Phase 4) | ❌ **Not available** — Work IQ MCP requires a delegated user token | ✅ Supported |

**Consequence for Phase 4:** Work IQ tools cannot be attached to an S2S agent.
To demo admin-governed M365 data access, the agent would need to be registered
(or re-registered) in **OBO** mode, which introduces a signed-in user and
per-user consent. We keep S2S for pillars 1–3 and document the OBO delta rather
than switching the baseline.

## Skill order

Invoke skills by describing the outcome, not by typing the skill name. For our
S2S standard-agent path:

```
a365-setup                 → "set up this project for Agent 365"
  └─ make-a365-agent       → "register this agent with Agent 365"   (Standard agent, S2S)
       └─ instrument-observability   → Phase 3 ("add observability to this agent")
a365-code-validator        → "validate my a365 code"                (standalone, Phase 3+)
```

Skills to **skip** on this path:

- `make-ai-teammate` / `make-ai-teammate` messaging — AI Teammate path, requires
  the Frontier preview program (agent user account). Out of scope.
- `add-workiq-tools` — requires OBO (see above). Deferred to the OBO variant.
- `test-local` (Agents Playground) — connects over the agent messaging endpoint,
  which standard agents don't have. N/A.

## What `make-a365-agent` does

- Creates the **agent identity blueprint** and an **agent identity** from it in
  Microsoft Entra, and grants the permissions the agent needs.
- Writes generated IDs and endpoints to **`a365.generated.config.json`**
  (git-ignored). No hand-authored `a365.config.json` is needed for a standard
  agent.
- Always shows a **dry-run preview before applying anything**; `a365 setup all`
  is **idempotent** and safe to re-run.

### Permissions — how they are determined and granted

The exact set of blueprint permissions is surfaced by the skill's **dry-run
preview** for this specific agent, and can be re-verified read-only afterward
with `a365 query-entra` (used by `a365-code-validator`). We record the actual
granted scopes here **after** the dry run rather than hardcoding a guessed list,
because the SDK never grants permissions silently:

- No automatic grants — permissions are always explained and require either
  `a365 setup all` (developer-run) or, for Work IQ, `a365 setup permissions mcp`
  (Global Administrator).
- The observability exporter (Phase 3) acquires an **S2S token for the
  Observability API scope** `api://9b975845-388f-4429-889e-eab1ef63949c/.default`
  via the MSAL FMI 3-hop chain, refreshed every ~50 minutes. This is the one
  concrete scope documented for the S2S path; the rest are shown in the dry run.

> Action for the operator: when we run the dry run, paste its permission list
> back here so this file becomes the authoritative record for the demo.

## Prerequisites

| Requirement | Detail |
| --- | --- |
| Tenant | Agent 365 enabled. |
| One-time tenant setup | `a365 setup requirements`, run **once** by an **Application Administrator** (lightest; Cloud App Admin or GA also work). All developers then inherit the ready state. **GA is not required for this step.** |
| Registration identity | Sign in as **Global Administrator**, or **Agent ID Developer with a GA available** to complete the OAuth permission grants. |
| Azure | `az login` (opens the browser on macOS). An Azure subscription with permission to create resources. |
| Tooling | `a365` CLI (`dotnet tool install -g Microsoft.Agents.A365.DevTools.Cli`, `~/.dotnet/tools` on PATH), `gh` for the skills. |
| Skills installed | `gh skill add microsoft/agent365-skills`, then **restart the assistant** and confirm with `/skills list`. |
| Observability license (Phase 3) | At least one user with **Microsoft 365 E7** or **Microsoft Agent 365** license — otherwise telemetry is dropped silently. |

## Execution

Run interactively. **Pause and get confirmation before** any step that changes
tenant state (blueprint creation, admin consent). Concretely:

1. `gh skill add microsoft/agent365-skills` → restart assistant → `/skills list`.
2. `az login`; confirm `a365 --version` resolves.
3. "set up this project for Agent 365" (`a365-setup`) — answer: **Standard agent
   (Agent, non AI Teammate)**, auth mode **S2S**.
4. Review the **dry-run preview** from `make-a365-agent`. **Stop here for
   approval** before applying.
5. Apply → `a365.generated.config.json` is written. Record the blueprint ID,
   agent identity ID, and the granted permissions back into this doc.

## The separate no-code path (deferred)

There is a **second, unrelated** way to get the Gemini agent into the Agent 365
registry — **Google Vertex AI registry sync** — which requires a Google Cloud
project we don't have yet. It produces an **inventory-only ("Unmanaged")**
record with no telemetry and no enforcement, distinct from the SDK-registered
managed record. See [DEFERRED.md](DEFERRED.md).
