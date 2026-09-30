"""Push copy eval (eng review 7A). Run on every change to push.hook_prompt.

    set ANTHROPIC_API_KEY in your shell, then from backend/:
    .venv-test\\Scripts\\python scripts\\eval_push_copy.py

For each case in tests/evals/push_copy_cases.json it runs the live hook prompt,
then composes the final push exactly as the scheduler would (push.py). It FAILS
(exit 1) when a sensitive story:
  - comes back sensitive=false, or
  - would be sent with anything but the sober template.
Light stories are printed so you can judge the tone yourself.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import push as P  # noqa: E402

CASES = HERE / "tests" / "evals" / "push_copy_cases.json"
# Same model the server uses for push copy (server.py AI_MODEL: haiku unless
# AI_MODEL is set), so the eval judges what readers will actually get.
_ALIASES = {"sonnet": "claude-sonnet-4-5-20250929", "haiku": "claude-haiku-4-5-20251001"}
_RAW = os.environ.get("AI_MODEL", "haiku").strip()
MODEL = _ALIASES.get(_RAW.lower(), _RAW)


async def main() -> int:
    try:
        import anthropic
    except ImportError:
        print("pip install anthropic first")
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY in this shell first.")
        return 2
    client = anthropic.AsyncAnthropic()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    failures = 0

    async def one(case):
        prompt = P.hook_prompt(case["slot"], case["headline"], case["summary"])
        try:
            msg = await client.messages.create(model=MODEL, max_tokens=300,
                                               messages=[{"role": "user", "content": prompt}])
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        except Exception as e:  # an API failure counts as "no verdict" → sober
            raw = None
            print(f"  (API error: {e})")
        ai = P.parse_hook(raw)
        copy = P.compose_slot_copy(case["slot"], case["headline"], ai, [], "Asha", 0)
        return case, ai, copy

    results = await asyncio.gather(*(one(c) for c in cases))
    for case, ai, copy in results:
        tag = "SENSITIVE" if case["sensitive"] else "light"
        problems = []
        if case["sensitive"]:
            if ai and ai.get("sensitive") is False:
                problems.append("model said not sensitive")
            if not copy.sober:
                problems.append("would NOT be sent sober")
        if P.copy_problem(copy.title, copy.body, case["slot"], copy.sober, from_ai=False):
            problems.append("copy check failed")
        status = "FAIL" if problems else "ok  "
        failures += bool(problems)
        print(f"{status} [{tag:9}] {case['slot']:7} | {copy.title} | {copy.body}"
              + (f"   <-- {', '.join(problems)}" if problems else ""))
    print(f"\n{len(results) - failures}/{len(results)} passed. Read the light lines: would you send them?")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
