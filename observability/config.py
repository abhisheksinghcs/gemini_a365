# A365 Observability — best-effort instrumentation
"""Resolved Agent 365 configuration.

Reads the values `a365 setup all` stamped into the repo-root ``.env``. Accepts
both the explicit ``AGENT365_*`` names (what the observability reference uses) and
the CLI's own stamped names (``AGENT365OBSERVABILITY__*`` /
``CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*``), so it works out of the box.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# The CLI stamps the repo-root .env (not security_agent/.env).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value and not value.startswith("<<"):
            return value
    return default


TENANT_ID = _env(
    "AGENT365_TENANT_ID",
    "AGENT365OBSERVABILITY__TENANTID",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID",
)
AGENT_ID = _env("AGENT365_AGENT_ID", "AGENT365OBSERVABILITY__AGENTID", "AGENT_ID")
BLUEPRINT_ID = _env("AGENT365_BLUEPRINT_ID", "AGENT365OBSERVABILITY__AGENTBLUEPRINTID")
CLIENT_ID = _env(
    "AGENT365_CLIENT_ID",
    "AGENT365OBSERVABILITY__CLIENTID",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID",
)
CLIENT_SECRET = _env(
    "AGENT365_CLIENT_SECRET",
    "AGENT365OBSERVABILITY__CLIENTSECRET",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET",
)
AGENT_NAME = _env(
    "AGENT365_AGENT_NAME", "AGENT365OBSERVABILITY__AGENTNAME", default="gemini-secagent"
)
AGENT_DESCRIPTION = _env(
    "AGENT365_AGENT_DESCRIPTION",
    "AGENT365OBSERVABILITY__AGENTDESCRIPTION",
    default="SecurityResearchAssistant",
)

# Local dev (macOS) has no managed identity → default to client-secret auth.
USE_MANAGED_IDENTITY = _env("AGENT365_USE_MANAGED_IDENTITY", default="false").lower() == "true"

# S2S has no signed-in user; CallerDetails uses the blueprint sponsor so MAC shows activity.
SPONSOR_USER_ID = _env("AGENT365_SPONSOR_USER_ID", default=CLIENT_ID)
SPONSOR_USER_EMAIL = _env("AGENT365_SPONSOR_USER_EMAIL")
SPONSOR_USER_NAME = _env("AGENT365_SPONSOR_USER_NAME", default=AGENT_NAME)


def has_credentials() -> bool:
    """True when enough config is present to attempt token acquisition + export."""
    if not (TENANT_ID and AGENT_ID and CLIENT_ID):
        return False
    if USE_MANAGED_IDENTITY:
        return True
    return bool(CLIENT_SECRET)


A365_ENABLED = has_credentials()
