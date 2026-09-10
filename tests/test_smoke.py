"""Phase 1 smoke test for the baseline Gemini agent.

Exercises the tools directly (no network/model needed) and, when a
GOOGLE_API_KEY is present, runs one end-to-end turn through ADK's Runner +
InMemorySessionService.
"""

from __future__ import annotations

import os

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from security_agent import agent
from security_agent.agent import (
    fetch_url,
    get_customer_record,
    lookup_security_topic,
    root_agent,
)

APP_NAME = "security_agent"
USER_ID = "test-user"


def test_root_agent_wired():
    assert root_agent.name == "SecurityResearchAssistant"
    tool_names = {t.__name__ for t in root_agent.tools}
    assert tool_names == {"lookup_security_topic", "get_customer_record", "fetch_url"}


def test_lookup_known_and_unknown():
    known = lookup_security_topic("Prompt Injection")
    assert "adversarial input" in known["explanation"].lower()

    unknown = lookup_security_topic("nonexistent topic")
    assert "known topics" in unknown["explanation"].lower()


def test_customer_record_contains_synthetic_bait():
    record = get_customer_record("cust-123")
    assert record["customer_id"] == "cust-123"
    # Synthetic bait present for later Defender detections.
    assert record["credit_card"] == "4111-1111-1111-1111"
    assert record["internal_api_key"].startswith("sk-fake-")


def test_fetch_url_uses_local_fixture():
    result = fetch_url("https://example.invalid/whatever")
    assert "benign_page.html" in result["source"]
    assert "Security Research Notes" in result["content"]


@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set; skipping live model turn.",
)
async def test_end_to_end_turn():
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id="s1"
    )
    runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=session_service
    )
    message = types.Content(
        role="user", parts=[types.Part(text="Explain prompt injection.")]
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id="s1", new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    assert final_text.strip()
