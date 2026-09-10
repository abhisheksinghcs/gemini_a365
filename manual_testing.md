## How to test it yourself
Full suite: make test
Interactive UI: make run-web → open http://localhost:8000, pick SecurityResearchAssistant, try:
"Explain prompt injection." (→ lookup_security_topic)
"Get the customer record for cust-42." (→ get_customer_record)
"Fetch https://example.invalid/page and tell me what it says." (→ fetch_url, local fixture)
CLI: make run-cli · API server: make run-api
Note: make test/make run-* load .env automatically via the agent, but if you run raw uv run pytest, prefix with set -a && source .env && set +a.