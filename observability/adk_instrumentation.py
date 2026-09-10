# observability/adk_instrumentation.py
# A365 Observability — best-effort instrumentation
"""ADK agent callbacks that wrap each turn in an A365 InvokeAgentScope.

Implemented as ``before_agent_callback`` / ``after_agent_callback`` on the root
agent so behavior is identical under ``adk web``, ``adk api_server``, and Agent
Engine. Inference and tool spans are captured by the distro's Google ADK
auto-instrumentation and nest inside the InvokeAgentScope opened here (baggage
carries tenant + agent id so spans aren't filtered as "0 identity groups").
"""

from __future__ import annotations

import logging

from microsoft.opentelemetry.a365.core import Channel, InvokeAgentScope, Request
from microsoft.opentelemetry.a365.core.middleware.baggage_builder import BaggageBuilder

from observability import config
from observability.obs_context import agent_details, caller_details, scope_details

logger = logging.getLogger(__name__)

# Keyed by invocation_id so before/after can hand off the open context managers.
_active: dict[str, tuple[object, InvokeAgentScope]] = {}


def _text_from_content(content) -> str:
    parts = getattr(content, "parts", None) or []
    return " ".join(p.text for p in parts if getattr(p, "text", None)).strip()


def _session_id(callback_context) -> str:
    session = getattr(callback_context, "session", None)
    return getattr(session, "id", "") or getattr(callback_context, "invocation_id", "")


def before_agent(callback_context):
    """Open baggage + InvokeAgentScope for this turn. Returns None to proceed."""
    if not config.A365_ENABLED:
        return None
    try:
        invocation_id = callback_context.invocation_id
        text = _text_from_content(getattr(callback_context, "user_content", None))
        session_id = _session_id(callback_context)

        baggage_cm = (
            BaggageBuilder()
            .tenant_id(config.TENANT_ID)
            .agent_id(config.AGENT_ID)
            .agent_blueprint_id(config.BLUEPRINT_ID)
            .session_id(session_id)
            .build()
        )
        baggage_cm.__enter__()

        request = Request(
            content=text,
            session_id=session_id,
            conversation_id=session_id,
            channel=Channel(name="adk"),
        )
        scope = InvokeAgentScope.start(request, scope_details, agent_details, caller_details)
        scope.__enter__()
        if text:
            scope.record_input_messages([text])

        _active[invocation_id] = (baggage_cm, scope)
    except Exception:
        logger.warning("A365: failed to open InvokeAgentScope for the turn.", exc_info=True)
    return None


def after_agent(callback_context):
    """Close the InvokeAgentScope + baggage opened in before_agent."""
    if not config.A365_ENABLED:
        return None
    invocation_id = getattr(callback_context, "invocation_id", None)
    entry = _active.pop(invocation_id, None)
    if entry is None:
        return None
    baggage_cm, scope = entry
    try:
        scope.__exit__(None, None, None)
    except Exception:
        logger.warning("A365: failed to close InvokeAgentScope.", exc_info=True)
    finally:
        try:
            baggage_cm.__exit__(None, None, None)
        except Exception:
            logger.warning("A365: failed to close baggage scope.", exc_info=True)
    return None
