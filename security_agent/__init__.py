# A365 Observability — best-effort instrumentation
# Initialize the OpenTelemetry distro BEFORE importing the agent (which imports
# google.adk), so GenAI auto-instrumentation can patch the model libraries.
from observability.bootstrap import init_observability

init_observability()

from . import agent

__all__ = ["agent"]
