# Deferred items (need a Google Cloud / Vertex AI project)

These items cannot be done until the customer's **Google Cloud project** exists.
They are documented here so the demo can show them as "next steps" without
attempting them.

> Sources: [Connected platforms](https://learn.microsoft.com/microsoft-agent-365/admin/connected-platforms),
> [Connect existing agents](https://learn.microsoft.com/microsoft-agent-365/connect-existing-agents).

## 1. Google Vertex AI registry sync (no-code inventory)

A **separate path** from the SDK registration in
[PHASE2_REGISTRATION.md](PHASE2_REGISTRATION.md). Registry sync imports agents
from an external platform into the Agent 365 registry for **centralized
visibility only**.

### Managed (SDK) vs Unmanaged (synced)

| | **SDK-registered** (Phase 2) | **Registry-synced** (this section) |
| --- | --- | --- |
| Record type | **Managed** | **Unmanaged** (inventory only) |
| Telemetry / observability | ✅ Yes (Phase 3) | ❌ No |
| Policy enforcement / governance | ✅ Yes | ❌ No |
| How it's created | `make-a365-agent` in code | Admin center, no code |

Both records can appear for the **same workload** and are **not merged today**.
The SDK-registered record is the one to govern; the synced record is inventory.

### Steps (admin center, when the GCP project exists)

1. [Microsoft 365 admin center](https://admin.microsoft.com) → **Agents** →
   **All Agents**.
2. In the **Connected platforms** web part → **Manage** → **+ Connect a
   platform**.
3. Name + describe the connection; select **Google Vertex AI**; select the
   **region**; choose whether to import agents automatically.
4. Enter credentials → **Validate** → **Save**.
5. Use **Sync agents** to pull agents into the registry.

### Google Vertex AI credentials required

- **Google Cloud Region** — where the agents are deployed.
- **Google Vertex AI project ID**.
- **Service account secret key** with the **Vertex AI Administrator** role, or a
  custom role with:
  - `aiplatform.reasoningEngines.list`
  - `aiplatform.reasoningEngines.get`
  - `aiplatform.reasoningEngines.delete`

> Never commit the service-account key. `.gitignore` already excludes
> `*service-account*.json` / `*gcp*key*.json`.

## 2. Phase 7 — Deploy to Vertex AI Agent Engine

No Google Cloud project exists yet, so deployment is **documentation only**.

### Switch the model backend to Vertex (Option B)

In `security_agent/.env`, comment out the Gemini Developer API key and enable the
Vertex options (ADK 2.x names):

```dotenv
# Option A — Gemini Developer API (disable when moving to Vertex)
# GOOGLE_API_KEY=...

# Option B — Vertex AI
GOOGLE_GENAI_USE_ENTERPRISE=True
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-3.5-flash
```

The pinned model ID (`gemini-3.5-flash`) is intentionally concrete so the same
config resolves on the regional Vertex endpoint.

### Deploy + verify

1. `gcloud auth application-default login`.
2. Deploy to Agent Engine (per current ADK / Agent Engine docs).
3. Post-deploy checks:
   - Observability exporter still returns **HTTP 200** and spans still appear on
     the Activity page (Phase 3 gate).
   - The **"Unmanaged"** registry-sync record is expected alongside the managed
     SDK record (section 1).

## 3. Phase 4 — Work IQ tools (blocked by S2S, not by GCP)

Not GCP-dependent, but deferred for a different reason: Work IQ MCP requires a
**delegated (OBO) user token**, which the S2S baseline does not have. Enabling it
means registering an **OBO** variant of the agent and a Global Administrator
granting the Work IQ permissions (`a365 setup permissions mcp`). See the S2S vs
OBO comparison in [PHASE2_REGISTRATION.md](PHASE2_REGISTRATION.md).
