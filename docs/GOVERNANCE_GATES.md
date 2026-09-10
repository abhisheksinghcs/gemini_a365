# Two gates, two personas: how this agent is governed

Microsoft Agent 365 governs an agent through **two separate gates**, owned by two
different personas. This **S2S standard agent passed the first gate and never
enters the second** — by design.

## Gate 1 — Identity gate (Microsoft Entra) — governs *what* the agent can access

Passed during `a365 setup all --authmode s2s`. Persona: **identity / app
administrator**. It has three parts:

1. **Tenant prerequisite** — `a365 setup requirements`, run once by an
   **Application Administrator**, registers the CLI's app so setup can proceed.
2. **Identity creation** — an **agent identity blueprint** and a **per-agent
   identity** are created in Entra (the agent's service principal).
3. **Admin consent** — a **Global Administrator consents** to the blueprint's
   application permissions. For this lab the consented permissions are (by name):
   - `access_agent_as_user` — the blueprint scope added during setup.
   - `Agent365.Observability.OtelWrite` — the Observability API app role (granted
     out-of-band via `az rest` after the CLI's inline grant returned 403).

   > `resourceConsents` in `a365.generated.config.json` is currently empty; the
   > authoritative permission list lives on the blueprint in Entra. Referenced by
   > **name only** — no IDs or secrets here.

**Easy to miss:** when the operator is already a **Global Admin**, the consent
step happens **inline** during `setup all` — there's no separate approval screen,
so it's easy to not realize a GA consent just occurred.

## Gate 2 — Distribution gate (M365 admin center → Agents → All agents → **Requests**) — governs *who* can use the agent

Persona: **Microsoft 365 / collaboration administrator**. This approval queue is
triggered **only** by publishing/surfacing an agent to users:

- **Pending review** — an agent package is published to the tenant.
- **Pending update** — an update to a published agent is published.
- **Pending activate** — blueprint activation is requested so users can create
  instances (the AI-teammate path).

**Our agent was never published or surfaced in Teams/Copilot**, so **no request
was generated**. The **Requests** tab is empty for it. This is **expected
behavior, not a bypass** — registration (`setup all`) makes an agent *visible in
the registry*; only `a365 publish` (or an activation request) enters the
distribution gate.

## Does it apply to this lab?

| Request state | What triggers it | Applies to this lab? |
| --- | --- | --- |
| **Pending review** | Publish an agent package (`a365 publish`) | Only if we run `a365 publish` in Phase 4 |
| **Pending update** | Publish an update to a published agent | Only if we run `a365 publish` in Phase 4 |
| **Pending activate** | Request blueprint activation for user-created instances | **No** — the AI-teammate path is out of scope on this branch |

## Where to verify

- **Identity gate:** Entra admin center → **Agent identities** — the blueprint,
  the per-agent identity, and the sponsor; blueprint → **Permissions** for the
  consented app permissions.
- **Registry entry:** M365 admin center → **Agents → All agents** — the
  registration and its **Activity** page.
- **Distribution gate:** M365 admin center → **Agents → All agents → Requests** —
  should be **empty for this agent** (nothing was published).
