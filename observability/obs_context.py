# observability/obs_context.py
# A365 Observability — best-effort instrumentation
"""Shared A365 observability context (agent + caller identity).

For an S2S agent there is no signed-in user, so ``CallerDetails`` uses the
blueprint sponsor identity — without it, traces don't surface in the Microsoft
365 admin center / Defender.
"""

from __future__ import annotations

from microsoft.opentelemetry.a365.core import (
    AgentDetails,
    CallerDetails,
    InvokeAgentScopeDetails,
    ServiceEndpoint,
    UserDetails,
)

from observability import config

agent_details = AgentDetails(
    agent_id=config.AGENT_ID,
    agent_name=config.AGENT_NAME,
    agent_description=config.AGENT_DESCRIPTION,
    agent_blueprint_id=config.BLUEPRINT_ID,  # MAC roll-up to the blueprint
    tenant_id=config.TENANT_ID,
)

caller_details = CallerDetails(
    user_details=UserDetails(
        user_id=config.SPONSOR_USER_ID,
        user_email=config.SPONSOR_USER_EMAIL,
        user_name=config.SPONSOR_USER_NAME,
    ),
)

# The ADK dev host; hostname/port are informational for the span.
scope_details = InvokeAgentScopeDetails(
    endpoint=ServiceEndpoint(hostname="localhost", port=8000),
)
