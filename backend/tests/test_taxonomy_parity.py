"""The app's lib/taxonomy.js must mirror categories.py: a chip or state the
server doesn't know would filter to nothing (or the reverse)."""

import pathlib
import re

import pytest

import categories as C

JS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "taxonomy.js"
pytestmark = pytest.mark.skipif(not JS.exists(), reason="frontend not in this checkout")


def _object(name: str) -> dict:
    src = JS.read_text(encoding="utf-8")
    body = re.search(rf"export const {name} = \{{(.*?)\n\}};", src, re.S).group(1)
    return {k: re.findall(r'"([^"]+)"', v) for k, v in re.findall(r"(\w+):\s*\[(.*?)\]", body, re.S)}


def test_subcategories_match():
    assert _object("SUBCATEGORIES") == C.SUBCATEGORIES_V2


def test_state_regions_match():
    assert _object("STATE_REGIONS") == C.STATE_REGIONS


def test_top_chips_are_v2_categories_plus_states():
    src = JS.read_text(encoding="utf-8")
    chips = re.findall(r'"([^"]+)"', re.search(r"TOP_CHIPS = \[(.*?)\];", src, re.S).group(1))
    assert chips[0] == "All" and chips[-1] == "States"
    assert sorted(chips[1:-1]) == sorted(C.CATEGORIES_V2)
