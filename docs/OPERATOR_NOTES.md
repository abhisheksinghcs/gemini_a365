# Operator notes & gotchas

Hard-won lessons from wiring this Gemini-native (Google ADK) agent into Microsoft
Agent 365. Read this before running the setup yourself — it will save you the
detours we took. Companion docs: [PHASE2_REGISTRATION.md](PHASE2_REGISTRATION.md)
(the registration plan + recorded result) and [DEFERRED.md](DEFERRED.md).

---

## TL;DR — the five things that will bite you

1. **Run `a365 setup all` yourself, in a real terminal** — not through an AI
   assistant's terminal. It is interactive (device-code sign-in + admin consent)
   and long-running; an agent-driven shell can't see those prompts and it *looks*
   hung when it's actually waiting.
2. **`a365 setup all` calls `api.nuget.org` in its prerequisites step.** If your
   org blocks that domain, setup hangs. Use **`--skip-requirements`**.
3. **S2S permission grants need a directory admin.** The CLI's own token gets
   `403` assigning the observability app role — finish it out-of-band with
   `az rest` (no PowerShell needed on macOS).
4. **Gemini model IDs churn.** `gemini-2.5-flash` is already retired for new API
   keys. Pin a concrete, current ID (`gemini-3.5-flash`), never a `*-latest`
   alias.
5. **Secrets are written in plaintext** to `.env` and
   `a365.generated.config.json` (macOS has no DPAPI). Both are git-ignored — keep
   it that way, and never paste them into chat/tickets.

---

## When to use Skills vs CLI vs manual

The Agent 365 **Skills** (`a365-setup`, `make-a365-agent`, …) are a guided
wrapper over the **`a365` CLI**. They're great for *deciding what to run and in
what order*, but the actual provisioning command is still the CLI, and some steps
are genuinely interactive. Rule of thumb:

| Task | Best tool | Why |
| --- | --- | --- |
| Deciding the path (agent kind, auth mode, capability order) | **Skills** | They encode the correct order: `a365-setup → make-a365-agent → instrument-observability`. |
| Detecting stack / reading existing config | **Skills** | Read-only; cheap; writes `.a365-workspace-detection.local.json`. |
| Previewing what will be created | **CLI dry-run** | `a365 setup all … --dry-run` changes nothing. Safe to run anytime. |
| The real `a365 setup all` (blueprint, identity, consent) | **CLI, run manually** | Interactive device-code + admin-consent prompts; long-running. See below. |
| S2S app-role grant that 403'd | **`az rest` (or PowerShell)** | The CLI can't self-grant app roles; an admin token must. |
| Everyday app work (code, run, test) | **Neither** | Pure local dev; no A365 tooling needed. |

### Why "manual" for `a365 setup all`

We tried driving it through the assistant. After device-code sign-in the process
sat at ~0% CPU for minutes with no config written — it *looked* stalled but was
actually blocked on a network call (see nuget.org below) and later on prompts the
assistant's terminal couldn't surface. Running it in your own terminal, you see
every prompt and step (`[1/8]…[8/8]`) live. Use the assistant to **prepare and
explain**, then **you** run the provisioning command.

---

## Environment gotchas (macOS)

### NuGet / blocked `api.nuget.org`
- Org policy here blocks `api.nuget.org` and provides
  `https://packagefeedproxy.microsoft.io/nuget/v3/index.json` instead.
- All local NuGet configs already disable `nuget.org` and enable the proxy, and
  the repo ships a [`nuget.config`](../nuget.config) with `<clear/>` + the proxy
  so `dotnet` restores here never touch the blocked feed.
- **But** `a365 setup all`'s *prerequisites* step calls `api.nuget.org`
  **directly** — outside NuGet source resolution — so config alone doesn't stop
  it. The blocked call hangs and setup stalls.
- **Fix:** `a365 setup all … --skip-requirements`. The remaining steps don't need
  nuget.org. Long-term: ask IT to allowlist `api.nuget.org` for the dev machine,
  or run the one-time registration from an unfiltered network.

### Device-code auth
- On recent macOS, `a365` prints *"Browser authentication is not supported on
  this platform"* and falls back to **device code**: open
  `https://login.microsoft.com/device`, enter the code, sign in as your admin.
  This is expected, not an error.

### Gemini model IDs
- Pin a concrete model (`GEMINI_MODEL=gemini-3.5-flash`), not `*-latest` — the
  same value must resolve later on regional Vertex endpoints.
- If you get `404 NOT_FOUND … no longer available to new users`, the model ID
  retired; list current ones: `client.models.list()` filtered on
  `generateContent`.

### ADK Web is dev-only
- If port 8000 is taken (macOS AirPlay Receiver holds 5000/7000; other dev
  servers often hold 8000), use `make run-web PORT=8080`.

---

## Auth model — S2S vs OBO (pick before you register)

| | **S2S** (this agent) | **OBO** |
| --- | --- | --- |
| Token subject | The agent's own service principal | A signed-in user |
| Needs a user in the loop | No | Yes |
| Observability | ✅ | ✅ |
| Work IQ tools | ❌ (needs a delegated user token) | ✅ |
| Admin needed at setup | GA / App Admin for app-role grants | none for the grants |

We chose **S2S** because the Gemini runtime has no inbound Microsoft 365 user
token. Consequence: **Work IQ (Phase 4) isn't available** without switching to an
OBO variant.

---

## The S2S app-role grant (the `403` you will hit)

`a365 setup all` tries to assign `Agent365.Observability.OtelWrite` to the agent
identity and fails with `403 Authorization_RequestDenied` — its delegated token
can't assign app roles. Complete it with an admin token. **PowerShell-free path
(macOS/zsh):**

```zsh
OBS_APP_ID=9b975845-388f-4429-889e-eab1ef63949c
OBS_SP_ID=$(az ad sp show --id $OBS_APP_ID --query id -o tsv)
ROLE_ID=$(az ad sp show --id $OBS_APP_ID \
  --query "appRoles[?value=='Agent365.Observability.OtelWrite'].id | [0]" -o tsv)
AGENT_SP_ID=<agenticAppId from a365.generated.config.json>

az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$AGENT_SP_ID/appRoleAssignments" \
  --body "{\"principalId\":\"$AGENT_SP_ID\",\"resourceId\":\"$OBS_SP_ID\",\"appRoleId\":\"$ROLE_ID\"}"

# verify
az rest --method GET \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$AGENT_SP_ID/appRoleAssignments" \
  --query "value[].{appRoleId:appRoleId,resourceId:resourceId}" -o table
```

- `az rest` uses your signed-in Azure CLI identity, which *does* carry
  `AppRoleAssignment.ReadWrite.All`, so it succeeds where the a365 CLI's app
  didn't — **provided your account holds GA / Privileged Role Admin / App Admin**.
- `400 "Permission being assigned already exists"` = already granted; you're done.
- The PowerShell equivalent (`Connect-MgGraph` + `New-MgServicePrincipalAppRoleAssignment`)
  works too if you have PowerShell 7 and the Microsoft.Graph module (from
  PSGallery, not nuget.org).

---

## Config files — input vs output

| File | Role | Committed? |
| --- | --- | --- |
| `a365.config.json` | **Input** — declared params (tenant, client app, names, `aiTeammate`, `useBlueprint`). Optional for standard agents; required + hand-authored for AI Teammates. | git-ignored |
| `a365.generated.config.json` | **Output/state** — real Entra IDs the CLI created + the client secret + `completed`. Source of truth for created resources; downstream skills read it. | git-ignored |
| `.env` (root) | A365 runtime settings the CLI stamped (client id/secret, tenant, observability). | git-ignored |
| `.a365-workspace-detection.local.json` | Skills' detection cache (stack, auth mode). Safe to delete; rebuilt on next `a365-setup`. | git-ignored |

- **`"completed": false`** in the generated config just means the CLI didn't run
  *every* step itself. If you finished the app-role grant out-of-band (as above),
  the flag stays `false`; re-running `a365 setup all --skip-requirements`
  (idempotent) reconciles it.

---

## Licensing traps (telemetry silently disappears)

Even with everything wired correctly, telemetry is dropped **silently** unless:
- At least one user in the tenant holds a **Microsoft 365 E7** or **Microsoft
  Agent 365** license, **and**
- Each run emits a valid **`invoke_agent`** span at its root (tool/inference
  spans nest inside it). No root span → spans stay queryable in Defender advanced
  hunting but never appear on the Activity page / Defender / Purview surfaces.

---

## Secrets hygiene

- The CLI prints the blueprint **client secret in plaintext** and stores it
  unprotected (`agentBlueprintClientSecretProtected: false`) because macOS has no
  DPAPI. It lives in `.env` and `a365.generated.config.json`.
- Both are git-ignored — verify with `git check-ignore .env a365.generated.config.json`.
- Never paste secrets into chat, tickets, or logs. To rotate: Entra portal →
  the Blueprint app registration → **Certificates & secrets** → replace, then
  update the `…CLIENTSECRET` keys in `.env`. (`a365 setup blueprint` has no
  rotate flag, only `--show-secret`.)

---

## Observability (Phase 3) gotchas

- **The reference's `uv` override pin is stale.** `instrument-observability`'s
  Python reference tells you to pin `opentelemetry-sdk>=1.38,<1.39` for Google
  ADK projects. That was for an **older ADK** — **ADK 2.8 requires OTel ≥1.39**
  (`opentelemetry-sdk>=1.39,<=1.42.1`), and current `microsoft-opentelemetry`
  (1.3.9) also wants ≥1.39. Applying the `<1.39` pin makes `uv sync` **fail** as
  unsatisfiable. **Fix: don't add the override at all** — default resolution
  installs a compatible OTel (1.40) that satisfies both.
- **Use the unified distro only.** `microsoft-opentelemetry`, imported as
  `from microsoft.opentelemetry import use_microsoft_opentelemetry`. Do **not**
  add legacy `microsoft-agents-a365-observability-*` packages or call
  `*Instrumentor().instrument()` — that produces duplicate spans.
- **ADK has no Agents-SDK host**, so the reference's `TurnContext` /
  `ObservabilityHostingManager` wiring doesn't apply. Adaptation that works under
  `adk web` / `adk api_server` / Agent Engine:
  - bootstrap `use_microsoft_opentelemetry(...)` **before** importing `google.adk`
    (in `security_agent/__init__.py`);
  - run the S2S token service on a **daemon thread** with its own event loop
    (no aiohttp startup hook to attach to);
  - open `InvokeAgentScope` in `before_agent_callback`, close it in
    `after_agent_callback` on the root agent (same task → inference/tool spans
    nest correctly).
- **`a365_use_s2s_endpoint=True` is mandatory for S2S** — else the exporter posts
  to the OBO endpoint and 401s.
- **Local dev uses client-secret FMI** (`AGENT365_USE_MANAGED_IDENTITY=false`);
  managed identity only exists on Azure. The 3-hop chain works from macOS.
- **Benign noise:** `No module named 'agents'` (distro probing the OpenAI Agents
  SDK we don't use) and an MSAL static-`client_assertion` `DeprecationWarning`.
- **Gemini can 503 ("high demand")** transiently — `telemetry-check` retries.
- **Verification is client-side.** `make telemetry-check` proves the span tree +
  token; the Activity page also needs a tenant user with an **E7 / Agent 365**
  license or telemetry is dropped silently even on HTTP 200.

---

## Branch strategy — three iterations

This repo is built as three progressive, demo-able iterations:

| Branch | Iteration | Identity / auth | Demonstrates |
| --- | --- | --- | --- |
| `main` | **1. Plain ADK agent** | none (Gemini only) | the "before" — zero Microsoft dependencies |
| `a365-integration` | **2. S2S agent** | blueprint + **S2S** | observability → threat protection → governance |
| *future* (`ai-teammate`) | **3. AI Teammate** | agentic-user / **OBO** + Work IQ | Teams + Copilot delivery, on-behalf-of user data |

- Iteration **2 stays S2S only** — it matches the telemetry/threat/governance
  lab, and Work IQ (Phase 4) is genuinely unavailable on S2S, so that capability
  is deferred to iteration 3 by design (not as a compromise).
- Iteration **3 branches from `a365-integration`**, inheriting all observability
  /threat/governance work, then adds the hosting layer (CEA or AI Teammate),
  OBO/agentic-user auth, and Work IQ. The clean diff is the "what it takes to
  become a Teammate" story.
- **AI Teammate needs the Frontier preview program** (agent user account +
  mailbox). Without it, the **CEA** (a bot users chat with, `a365 setup all
  --m365`) is the no-preview fallback for Teams/Copilot delivery.
- To add OBO to an existing S2S blueprint later (idempotent):
  `a365 setup all --agent-name gemini-secagent --authmode both --skip-requirements`.
