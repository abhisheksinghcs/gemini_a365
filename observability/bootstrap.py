# observability/bootstrap.py
# A365 Observability — best-effort instrumentation
"""Initialize the Microsoft OpenTelemetry distro for the S2S agent.

Call :func:`init_observability` BEFORE importing ``google.adk`` so the distro's
GenAI auto-instrumentation can patch the model libraries. Idempotent.

The S2S token service runs on a daemon thread with its own event loop, so it
works identically under ``adk web``, ``adk api_server``, and Agent Engine (none
of which give us a startup hook like the Agents SDK host does).
"""

from __future__ import annotations

import asyncio
import logging
import threading

from microsoft.opentelemetry import use_microsoft_opentelemetry

from observability import config, token_cache
from observability.observability_token_service import (
    acquire_initial_token,
    run_token_service,
)

logger = logging.getLogger(__name__)

_initialized = False
_token_thread_started = False


def _resolver(agent_id: str, tenant_id: str) -> str:
    """Exporter reads the current S2S token from the in-memory cache per export."""
    return token_cache.get_cached_token(agent_id, tenant_id) or ""


def init_observability() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    use_microsoft_opentelemetry(
        enable_a365=config.A365_ENABLED,
        a365_enable_observability_exporter=True,  # REQUIRED to actually export spans
        a365_use_s2s_endpoint=True,               # S2S posts to /observabilityService/
        a365_token_resolver=_resolver,
    )

    if config.A365_ENABLED:
        _start_token_thread()
    else:
        logger.warning(
            "A365 observability disabled — credentials missing. Run 'a365 setup all' "
            "or set AGENT365_* env vars in the repo-root .env."
        )


def _start_token_thread() -> None:
    global _token_thread_started
    if _token_thread_started:
        return
    _token_thread_started = True

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        args = (
            config.TENANT_ID,
            config.AGENT_ID,
            config.CLIENT_ID,
            config.CLIENT_SECRET,
            config.USE_MANAGED_IDENTITY,
        )
        try:
            loop.run_until_complete(acquire_initial_token(*args))
        except Exception:
            logger.warning("Initial A365 token acquisition failed; background loop will retry.", exc_info=True)
        try:
            loop.run_until_complete(run_token_service(*args))
        finally:
            loop.close()

    threading.Thread(target=_run, name="a365-obs-token", daemon=True).start()
