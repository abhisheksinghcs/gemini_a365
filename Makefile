# Gemini-native ADK agent wrapped in Microsoft Agent 365 — task runner.
# macOS / zsh / Homebrew. Run `make help` for the target list.

.DEFAULT_GOAL := help
SHELL := /bin/zsh

# Port for `adk web`. On macOS, AirPlay Receiver can hold 5000/7000 and other
# dev servers often hold 8000 — override with `make run-web PORT=8080`.
PORT ?= 8000

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install toolchain (brew) + sync Python deps (uv)
	@command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
	brew install uv gh azure-cli dotnet-sdk
	uv sync --extra dev

.PHONY: run-web
run-web: ## Run the agent in ADK Web (dev only) on $(PORT)
	uv run adk web --port $(PORT)

.PHONY: run-cli
run-cli: ## Run one interactive CLI session (adk run)
	uv run adk run security_agent

.PHONY: run-api
run-api: ## Serve the agent programmatically (adk api_server)
	uv run adk api_server

.PHONY: test
test: ## Run the pytest smoke suite
	uv run pytest -q

# --- Later phases (files added in Phase 3 / Phase 5) -----------------------

.PHONY: a365-validate
a365-validate: ## (Phase 2/3) Run the a365-code-validator skill flow
	@echo "Run the a365-code-validator skill, then: a365 validate  (see docs/)"

.PHONY: telemetry-check
telemetry-check: ## (Phase 3) Check the OpenTelemetry exporter health
	@test -f scripts/telemetry_check.py \
		&& uv run python scripts/telemetry_check.py \
		|| echo "Not yet implemented — added in Phase 3."

.PHONY: attack-run
attack-run: ## (Phase 5) Run the full adversarial corpus
	@test -f attacks/run.py \
		&& uv run python attacks/run.py \
		|| echo "Not yet implemented — added in Phase 5."

.PHONY: attack-known
attack-known: ## (Phase 5) Run ONLY the operator-supplied known trigger
	@test -f attacks/run.py \
		&& uv run python attacks/run.py --only known-trigger \
		|| echo "Not yet implemented — added in Phase 5."

.PHONY: attack-show
attack-show: ## (Phase 5) Print/copy the known trigger for manual paste
	@test -f attacks/run.py \
		&& uv run python attacks/run.py --show-trigger \
		|| echo "Not yet implemented — added in Phase 5."
