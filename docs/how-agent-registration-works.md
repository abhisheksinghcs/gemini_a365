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

> **Recorded 2026-09-10:** see [Result](#result--executed-2026-09-10). The S2S
> app role (`Agent365.Observability.OtelWrite`) was granted out-of-band via
> Azure CLI (`az rest`) and is now **assigned**.

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

## Result — executed 2026-09-10

Registration ran via `a365 setup all --agent-name gemini-secagent --authmode s2s
--skip-requirements` (the `--skip-requirements` flag is required in this
environment — see [Known issue](#known-issue-nugetorg-blocked-by-it) below).

Created (concrete GUIDs live in the git-ignored `a365.generated.config.json` and
root `.env`, which are the source of truth — kept out of this committed doc):

| Artifact | Name | Status |
| --- | --- | --- |
| Blueprint application | `gemini-secagent Blueprint` | ✅ created |
| Blueprint service principal | — | ✅ created |
| Blueprint scope | `access_agent_as_user` | ✅ added |
| Blueprint client secret | — | ✅ created (stored in `.env`; **rotated after exposure**) |
| Agent identity | `gemini-secagent Identity` | ✅ created |
| Agent registration | `gemini-secagent Agent` | ✅ registered — visible in the catalog |
| Sponsor / Owner | the signing-in admin user | ✅ set |
| Messaging endpoint | — | ⏭️ skipped (non-M365 agent) |

### Observability app-role grant — ✅ granted (was pending)

The S2S app-role assignment **`Agent365.Observability.OtelWrite`** on the
Observability API (`appId 9b975845-388f-4429-889e-eab1ef63949c`) initially failed
with **HTTP 403 `Authorization_RequestDenied`** — the a365 CLI's delegated token
lacked rights to assign app roles. This grant is **required for Phase 3 telemetry**.

It was completed out-of-band with **Azure CLI** (no PowerShell needed) by an
admin whose signed-in token can create app-role assignments:

```zsh
# Resolve the Observability API SP + role, then assign it to the agent identity SP
OBS_APP_ID=9b975845-388f-4429-889e-eab1ef63949c
OBS_SP_ID=$(az ad sp show --id $OBS_APP_ID --query id -o tsv)
ROLE_ID=$(az ad sp show --id $OBS_APP_ID \
  --query "appRoles[?value=='Agent365.Observability.OtelWrite'].id | [0]" -o tsv)
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/<AGENT_SP_ID>/appRoleAssignments" \
  --body "{\"principalId\":\"<AGENT_SP_ID>\",\"resourceId\":\"$OBS_SP_ID\",\"appRoleId\":\"$ROLE_ID\"}"
```

Verified with `GET .../servicePrincipals/<AGENT_SP_ID>/appRoleAssignments`. The
concrete `<AGENT_SP_ID>` is in `a365.generated.config.json`. The PowerShell path
(`Connect-MgGraph` + `New-MgServicePrincipalAppRoleAssignment`) that the CLI
prints is equivalent for environments that have PowerShell 7.

### Known issue — nuget.org blocked by IT

`a365 setup all`'s **prerequisites** step calls `api.nuget.org` directly, which
this tenant's IT content filter blocks; the call hangs and setup stalls. All
local NuGet configs already route to the org proxy
(`packagefeedproxy.microsoft.io/nuget`), but the CLI reaches nuget.org outside
NuGet source resolution. **Workaround:** pass `--skip-requirements` (the rest of
setup does not need nuget.org). Longer-term: have IT allowlist `api.nuget.org`
for the dev machine, or run the one-time registration from an unfiltered network.

## Registration vs. Publish (why the agent shows up without `a365 publish`)

A common confusion: the agent appears in the M365 admin center **registry**
(Agents → All agents) with an **Activity** page after `a365 setup all` alone —
no `a365 publish` needed. These are two different things:

| | Comes from | Produces |
| --- | --- | --- |
| **Registration** | `a365 setup all` (its "Agent Registration" step) | The agent listed in **Agents → All agents** + its **Activity** page. |
| **Publish** | `a365 publish` → `manifest.zip` → admin upload | An installable **Teams / M365 app** users can add and chat with. |

- The CLI's own `publish --use-blueprint` help says it plainly:
  *"Registration is handled by `a365 setup all`."* Our Setup Summary showed the
  step: `6. Agent Registration  registered  'gemini-secagent Agent'`.
- `a365 publish` only *"updates the ID values in `manifest.json` and creates a
  `manifest.zip` package for uploading to the Microsoft 365 admin center"* — i.e.
  it packages a **Teams/M365 app**. It needs a `manifest.json` and a messaging
  endpoint, which a **standard S2S agent doesn't have** (our Phase 2 skipped the
  messaging endpoint: *"Messaging endpoint: skipped (non-M365 agent)"*).

So registry visibility + telemetry (Phases 2–3) never need `publish`. You only
run `publish` on the **AI-Teammate branch** (iteration 3), where the agent gains
a hosting layer + messaging endpoint and becomes a Teams/Copilot app people can
install.

## The separate no-code path (deferred)

There is a **second, unrelated** way to get the Gemini agent into the Agent 365
registry — **Google Vertex AI registry sync** — which requires a Google Cloud
project we don't have yet. It produces an **inventory-only ("Unmanaged")**
record with no telemetry and no enforcement, distinct from the SDK-registered
managed record. See [DEFERRED.md](DEFERRED.md).
