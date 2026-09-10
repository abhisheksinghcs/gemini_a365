# Demo script — 20-minute customer walkthrough

Order: baseline → register → telemetry → threat protection → governance. Full
control details are in [CONTROLS_TEST_MATRIX.md](CONTROLS_TEST_MATRIX.md).

## (1) Baseline — Gemini agent, no Microsoft dependencies
Run `make run-web`, show `SecurityResearchAssistant` answering in ADK Web. No
Entra, no telemetry — the "before".

## (2) Register — identity appears in Entra + the M365 registry
Show the blueprint + per-agent identity in Entra and the agent in the M365
admin center registry (with its Activity page).

- **Talking point — two gates, two personas:** the **identity gate** is passed
  (Entra: Application Admin ran `a365 setup requirements`, then GA consent to the
  blueprint permissions during `a365 setup all`). The **distribution gate is not
  applicable** because nothing was published — show the **empty Requests tab**
  (Agents → All agents → Requests). See [GOVERNANCE_GATES.md](GOVERNANCE_GATES.md).

## (3) Telemetry — one prompt → spans → hunting
Send a prompt; show `invoke_agent → inference → tool` spans on the Activity page,
then the same activity in Advanced Hunting (`CloudAppEvents`).

## (4) Threat protection — attack corpus → Defender
Run `make attack-run` (ideally the day before so ingestion completes); live, use
`make attack-show` and paste the known trigger, then walk to Defender alerts /
incident with prompt evidence → AI agents posture → hunting filtered on the
session id.

## (5) Governance — controls the audience can see
Conditional Access denial, block/unblock, and an agent management rule / template
from the matrix. Close with what changes on the AI-teammate branch (Work IQ +
`a365 publish` → the distribution gate) and the Purview appendix.
