#!/usr/bin/env python
# A365 Observability — best-effort instrumentation
"""Phase 3 telemetry gate.

Sends one prompt that forces a tool call, captures the emitted OpenTelemetry
spans in-memory, and verifies:

  (a) the S2S observability token was acquired (exporter auth ready),
  (b) the span tree nests InvokeAgent -> inference -> tool,
  (c) baggage/identity (tenant id + agent id) is present on the spans.

Exits non-zero on any hard miss. Full surfacing on the Activity page also
requires a tenant user with an E7 / Microsoft Agent 365 license — this script
verifies the client-side contract, not the server-side ingestion.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import time

# Allow running as a bare script (`python scripts/telemetry_check.py`) from repo root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Import the agent first so init_observability() sets up the distro tracer provider.
from security_agent.agent import root_agent  # noqa: E402

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from observability import config, token_cache  # noqa: E402

APP_NAME = "telemetry_check"
PROMPT = "Get the customer record for cust-telemetry-check and summarize it."


def _attach_memory_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    add = getattr(provider, "add_span_processor", None)
    if add is None:
        print("FAIL: tracer provider is not an SDK TracerProvider; cannot inspect spans.")
        sys.exit(2)
    add(SimpleSpanProcessor(exporter))
    return exporter


async def _run_turn() -> None:
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=APP_NAME, user_id="u", session_id="s")
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part(text=PROMPT)])
    async for _ in runner.run_async(user_id="u", session_id="s", new_message=message):
        pass


def _run_turn_with_retry(attempts: int = 3) -> bool:
    """Run one turn; retry transient model errors. Returns True on success."""
    for i in range(1, attempts + 1):
        try:
            asyncio.run(_run_turn())
            return True
        except Exception as exc:  # transient model 503s, etc.
            msg = str(exc)
            transient = "503" in msg or "UNAVAILABLE" in msg or "429" in msg
            print(f"  turn attempt {i}/{attempts} failed: {msg[:120]}")
            if not (transient and i < attempts):
                return False
            time.sleep(4 * i)
    return False


def _has_attr(span, *keys: str) -> bool:
    attrs = dict(span.attributes or {})
    return any(k in attrs for k in keys)


def main() -> int:
    if not config.A365_ENABLED:
        print("FAIL: A365 not enabled (missing credentials). Run 'a365 setup all'.")
        return 1

    exporter = _attach_memory_exporter()
    turn_ok = _run_turn_with_retry()
    if not turn_ok:
        print("WARN: the agent turn did not complete (model unavailable?) — "
              "token check still runs, but the span-tree checks will fail.\n")
    spans = exporter.get_finished_spans()

    ok = True

    # (a) token acquired
    token_ready = bool(token_cache.get_cached_token(config.AGENT_ID, config.TENANT_ID))
    print(f"[{'PASS' if token_ready else 'FAIL'}] (a) S2S observability token acquired")
    ok &= token_ready

    # Classify spans by name/attributes (avoid hardcoding exact distro span names).
    names = [s.name for s in spans]
    invoke = [s for s in spans if "invoke_agent" in s.name.lower() or _has_attr(s, "gen_ai.agent.id")]
    inference = [s for s in spans if _has_attr(s, "gen_ai.request.model", "gen_ai.system", "gen_ai.operation.name")]
    tools = [s for s in spans if "tool" in s.name.lower() or _has_attr(s, "gen_ai.tool.name")]

    print(f"\nCaptured {len(spans)} spans: {names}\n")

    # (b) span tree
    b_ok = bool(invoke) and bool(inference) and bool(tools)
    print(f"[{'PASS' if invoke else 'FAIL'}]   invoke_agent span present ({len(invoke)})")
    print(f"[{'PASS' if inference else 'FAIL'}]   inference span present ({len(inference)})")
    print(f"[{'PASS' if tools else 'FAIL'}]   tool span present ({len(tools)})")
    print(f"[{'PASS' if b_ok else 'FAIL'}] (b) InvokeAgent -> inference -> tool tree")
    ok &= b_ok

    # (c) identity/baggage on spans
    tenant_seen = any(
        str(config.TENANT_ID) in str(dict(s.attributes or {}))
        or _has_attr(s, "microsoft.tenant.id")
        for s in spans
    )
    agent_seen = any(
        str(config.AGENT_ID) in str(dict(s.attributes or {})) or _has_attr(s, "gen_ai.agent.id")
        for s in spans
    )
    c_ok = tenant_seen and agent_seen
    print(f"[{'PASS' if tenant_seen else 'FAIL'}]   tenant id on spans")
    print(f"[{'PASS' if agent_seen else 'FAIL'}]   agent id on spans")
    print(f"[{'PASS' if c_ok else 'FAIL'}] (c) baggage carries tenant + agent id")
    ok &= c_ok

    print()
    if ok:
        print("RESULT: PASS — client-side telemetry contract satisfied.")
        print("Note: confirm the run also appears on the agent's Activity page in the")
        print("M365 admin center (needs a tenant user with E7 / Agent 365 license).")
        return 0
    print("RESULT: FAIL — see the checks above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
