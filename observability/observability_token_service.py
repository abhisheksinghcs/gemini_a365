# observability/observability_token_service.py
# A365 Observability — best-effort instrumentation
# A365 auth mode: S2S — 3-hop FMI token chain (direct HTTP POST + MSAL)
#   Hop 1+2: Blueprint (MSI or client secret) → T1 via token endpoint POST + fmi_path → Agent Identity
#   Hop 3:   Agent Identity uses T1 as assertion → Observability API token
"""Mints and refreshes the S2S access token the A365 exporter uses.

The Phase 3 OpenTelemetry exporter attaches an access token to every POST to the
Agent 365 observability service. This agent runs service-to-service (no signed-in
user), so there is no user token to borrow — this module obtains one from the
agent's own credentials via the **Federated Managed Identity (FMI) 3-hop chain**
and keeps it fresh.

Why 3 hops
----------
An agent identity can't be authenticated directly; it's reached by exchanging the
blueprint's credentials through an FMI path::

    Blueprint (client secret [local] or Managed Identity [Azure])
      │  Hop 1+2: POST the token endpoint with scope=api://AzureADTokenExchange/.default
      │           and fmi_path=<agentId>   → T1 (the Agent Identity's token)
      ▼
    Agent Identity
      │  Hop 3: MSAL client-credentials using T1 as a client_assertion,
      │         scope=api://9b975845-388f-4429-889e-eab1ef63949c/.default
      ▼
    Observability API token   → cached for the exporter to read per export

Public API
----------
- ``acquire_initial_token(...)`` — run the chain once at startup (token ready
  before the first turn).
- ``run_token_service(...)`` — background loop; re-runs the chain every 50 min
  (tokens live ~60 min). Started on a daemon thread by ``bootstrap.py``.

Data flow
---------
This module writes the final token to ``token_cache`` (thread-safe, in-memory);
``bootstrap._resolver`` reads it back on each export. Nothing here talks to the
exporter directly.

Notes
-----
- **Hop 1+2 is a raw ``httpx`` POST** because MSAL Python does not yet support
  the ``fmi_path`` parameter (see ``_acquire_t1_via_client_secret``).
- Local dev uses the **client secret** (``AGENT365_USE_MANAGED_IDENTITY=false``);
  on Azure set it ``true`` to use ``ManagedIdentityCredential`` instead.
- The scaffold originates from the ``instrument-observability`` skill's Python
  reference and is kept close to verbatim so it tracks upstream changes.
"""

import asyncio
import logging
from datetime import timedelta

import httpx
import msal

from observability import token_cache

logger = logging.getLogger(__name__)

FMI_SCOPE = "api://AzureADTokenExchange/.default"
OBSERVABILITY_SCOPES = ["api://9b975845-388f-4429-889e-eab1ef63949c/.default"]
REFRESH_INTERVAL_SECONDS = 50 * 60  # 50 minutes


async def acquire_initial_token(tenant_id, agent_id, blueprint_client_id, blueprint_client_secret, use_managed_identity):
    """Acquire the first observability token before background services start."""
    await _acquire_and_register_token(tenant_id, agent_id, blueprint_client_id, blueprint_client_secret, use_managed_identity)


async def run_token_service(tenant_id, agent_id, blueprint_client_id, blueprint_client_secret, use_managed_identity):
    """Background token acquisition loop."""
    logger.info("ObservabilityTokenService started (use_managed_identity=%s).", use_managed_identity)
    while True:
        try:
            await _acquire_and_register_token(tenant_id, agent_id, blueprint_client_id, blueprint_client_secret, use_managed_identity)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to acquire observability token; will retry in %d seconds.", REFRESH_INTERVAL_SECONDS, exc_info=True)
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


async def _acquire_and_register_token(tenant_id, agent_id, blueprint_client_id, blueprint_client_secret, use_managed_identity):
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    token_url = f"{authority}/oauth2/v2.0/token"

    # Hop 1+2: Blueprint → T1 via FMI path
    if use_managed_identity:
        t1_token = await _acquire_t1_via_msi(token_url, blueprint_client_id, agent_id)
    else:
        t1_token = await _acquire_t1_via_client_secret(token_url, blueprint_client_id, blueprint_client_secret, agent_id)

    # Hop 3: Agent Identity uses T1 → Observability API token
    identity_app = msal.ConfidentialClientApplication(
        client_id=agent_id,
        client_credential={"client_assertion": t1_token},
        authority=authority,
    )
    obs_result = identity_app.acquire_token_for_client(scopes=OBSERVABILITY_SCOPES)
    if "access_token" not in obs_result:
        raise RuntimeError(f"Failed to acquire observability token: {obs_result.get('error_description', obs_result)}")

    token_cache.cache_token(agent_id, tenant_id, obs_result["access_token"], expires_in=timedelta(minutes=55))
    logger.info("Observability token registered for agent %s.", agent_id)


async def _acquire_t1_via_msi(token_url, blueprint_client_id, agent_id):
    """Acquire T1 token using Managed Identity (production) — direct HTTP POST."""
    from azure.identity.aio import ManagedIdentityCredential

    async with ManagedIdentityCredential() as credential:
        msi_token = await credential.get_token("api://AzureADTokenExchange")

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": blueprint_client_id,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": msi_token.token,
            "scope": FMI_SCOPE,
            "fmi_path": agent_id,
        })
        result = resp.json()

    if "access_token" not in result:
        raise RuntimeError(f"FMI T1 via MSI failed: {result.get('error_description', result)}")
    return result["access_token"]


async def _acquire_t1_via_client_secret(token_url, blueprint_client_id, blueprint_client_secret, agent_id):
    """Acquire T1 token using client secret (local dev) — direct HTTP POST with fmi_path."""
    # MSAL Python v1.34.0 does NOT properly support `fmi_path` as a kwarg.
    # Workaround: direct HTTP POST with fmi_path as form data until MSAL ships native support.
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": blueprint_client_id,
            "client_secret": blueprint_client_secret,
            "scope": FMI_SCOPE,
            "fmi_path": agent_id,
        })
        result = resp.json()

    if "access_token" not in result:
        raise RuntimeError(f"FMI T1 via client secret failed: {result.get('error_description', result)}")
    return result["access_token"]
