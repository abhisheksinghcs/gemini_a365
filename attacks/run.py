#!/usr/bin/env python
"""Phase 5 — adversarial corpus runner.

Drives ``attacks/corpus.yaml`` through the agent and records, per case, the
response + timestamp + **session id** so Microsoft Defender alerts can be
correlated back to the test case that produced them.

Transport: the in-process ADK ``Runner``. This emits the *same* A365 telemetry
as ``adk api_server`` (the exporter is wired on the agent at import via
``init_observability``; verified to POST HTTP 200), with far less orchestration.

Operator "known trigger" (never committed, never read by the agent):
  - ``A365_KNOWN_TRIGGER_FILE`` (default ``attacks/private/known_trigger.txt``)
  - ``A365_KNOWN_TRIGGER_PROMPT`` (inline fallback; the FILE wins if both set)
  - ``A365_KNOWN_TRIGGER_CLASS`` (optional Defender class tag)
Only this runner sends it. Its payload is never printed in normal logs — only a
sha256 — so ``adk web`` always starts clean and the demo keeps a real before/after.

Usage:
  python attacks/run.py                 # full corpus (+ known trigger if configured)
  python attacks/run.py --only <id>     # one case (e.g. known-trigger)
  python attacks/run.py --show-trigger  # print ONLY the trigger to stdout (for pbcopy)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import pathlib
import sys

# Allow running as a bare script from repo root.
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

CORPUS = REPO / "attacks" / "corpus.yaml"
RUNS_DIR = REPO / "attacks" / "runs"
APP_NAME = "attacks"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_corpus() -> list[dict]:
    data = yaml.safe_load(CORPUS.read_text(encoding="utf-8")) or {}
    return list(data.get("cases", []))


def load_known_trigger() -> tuple[str | None, str]:
    """Return (trigger_text, class). The FILE wins over the inline prompt."""
    file_env = os.environ.get("A365_KNOWN_TRIGGER_FILE", "attacks/private/known_trigger.txt")
    inline = os.environ.get("A365_KNOWN_TRIGGER_PROMPT", "")
    klass = os.environ.get("A365_KNOWN_TRIGGER_CLASS", "") or "operator-supplied"

    if file_env:
        path = REPO / file_env
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8"), klass
    if inline.strip():
        return inline, klass
    return None, klass


async def _run_case(case_id: str, prompt: str, run_ts: str) -> tuple[str, str, str]:
    """Send one prompt as a turn. Returns (session_id, response_text, error)."""
    # Lazy import so --show-trigger doesn't load the agent / start the token thread.
    from security_agent.agent import root_agent  # noqa: E402 (triggers observability bootstrap)
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    session_id = f"attack-{run_ts}-{case_id}"
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=APP_NAME, user_id="attacker", session_id=session_id)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final, error = "", ""
    try:
        async for event in runner.run_async(user_id="attacker", session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final = event.content.parts[0].text or ""
    except Exception as exc:  # e.g. Gemini 429 quota — record, keep going
        error = str(exc)[:200]
    return session_id, final, error


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the adversarial corpus against the agent.")
    parser.add_argument("--only", help="Run only the case with this id (e.g. known-trigger).")
    parser.add_argument("--show-trigger", action="store_true", help="Print ONLY the known trigger to stdout.")
    args = parser.parse_args()

    trigger_text, trigger_class = load_known_trigger()

    # --show-trigger: emit nothing but the trigger on stdout (Makefile pipes to pbcopy).
    if args.show_trigger:
        if not trigger_text:
            print("No known trigger configured (set A365_KNOWN_TRIGGER_FILE or _PROMPT).", file=sys.stderr)
            return 1
        sys.stdout.write(trigger_text)
        return 0

    cases = load_corpus()
    if trigger_text:
        # Appended as a secret case — payload is never logged, only a sha256.
        cases.append({"id": "known-trigger", "class": trigger_class, "prompt": trigger_text, "_secret": True})

    if args.only:
        cases = [c for c in cases if c.get("id") == args.only]
        if not cases:
            print(f"No case matching --only {args.only}", file=sys.stderr)
            return 1

    run_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"{run_ts}.jsonl"

    print(f"Running {len(cases)} adversarial case(s) → telemetry exports to Agent 365.\n")
    results: list[dict] = []
    known_session: str | None = None

    with out_path.open("w", encoding="utf-8") as out:
        for case in cases:
            cid = case.get("id", "?")
            klass = case.get("class", "")
            prompt = case.get("prompt", "")
            secret = case.get("_secret", False)

            session_id, final, error = asyncio.run(_run_case(cid, prompt, run_ts))

            rec = {
                "case_id": cid,
                "class": klass,
                "session_id": session_id,
                "timestamp": _now_iso(),
                "payload_sha256": _sha256(prompt),
                "error": error,
            }
            if secret:
                # Never persist or print the operator trigger payload/response.
                rec["response_len"] = len(final)
                known_session = session_id
                status = "ERR" if error else "ok"
                print(f"  [{cid}] class={klass} session={session_id} "
                      f"sha256={rec['payload_sha256'][:12]}… {status}")
            else:
                rec["prompt"] = prompt
                rec["response"] = final
                print(f"  [{cid}] class={klass} session={session_id} "
                      f"{'ERR: ' + error if error else 'ok'}")
            out.write(json.dumps(rec) + "\n")
            results.append(rec)

    print("\n=== summary (case → class → session id) ===")
    for r in results:
        print(f"  {r['case_id']:<26} {r['class']:<24} {r['session_id']}")
    print(f"\nResults written to: {out_path.relative_to(REPO)}")
    print("Correlate these session ids in Defender advanced hunting (see hunting/*.kql).")

    if known_session:
        print(f"\n>>> KNOWN-TRIGGER session id: {known_session}")
        print("    Paste it into the hunting queries to find its alert/incident.")

    errors = [r for r in results if r["error"]]
    if errors:
        print(f"\nNote: {len(errors)} case(s) errored (e.g. Gemini 429 quota). "
              "Re-run later or use a model with remaining quota.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
