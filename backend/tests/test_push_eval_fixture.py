"""The push copy eval fixture stays well-formed (runs offline; the live eval
is scripts/eval_push_copy.py)."""

import json
from pathlib import Path

import push as P

CASES = json.loads((Path(__file__).parent / "evals" / "push_copy_cases.json").read_text(encoding="utf-8"))["cases"]


def test_fixture_shape():
    assert len(CASES) == 25
    assert sum(c["sensitive"] for c in CASES) == 8
    for c in CASES:
        assert c["slot"] in P.SLOTS and c["headline"] and c["summary"]


def test_offline_path_is_always_sendable_and_sober_for_sensitive():
    # No model verdict (outage) and a model that wrongly calls everything light:
    # the Desk flag is the backstop for the second, sober templates for the first.
    for c in CASES:
        copy = P.compose_slot_copy(c["slot"], c["headline"], None, [], "Asha", 0)
        assert copy.sober
        assert P.copy_problem(copy.title, copy.body, c["slot"], True, from_ai=False) is None
