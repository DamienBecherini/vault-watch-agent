"""What may be ticked on the page of a check (static/rules.js, run with node): a lead dug deeper is always a lead
ticked, whatever the order of the clicks. Skipped where node is not installed (the GitHub runners have it)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RULES = Path(__file__).parent.parent / "src" / "vault_watch_agent" / "static" / "rules.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")


def node(script: str) -> subprocess.CompletedProcess:
    """`script` run by node after the rules, as one ES module (rules.js is one: its text, then the script, which reads
    them as R), given on its standard input (a long script would not fit a Windows command line)."""
    module = f"{RULES.read_text(encoding='utf-8')}\nconst R = LeadRules;\n{script}"
    return subprocess.run([NODE, "--input-type=module", "-"], input=module, capture_output=True, text=True,
                          encoding="utf-8", check=True)


def run(steps: list) -> list[dict]:
    """The state after each step: [{ticked, dug}] (sorted lists). A step: [rule, *arguments], applied in order from
    nothing ticked."""
    script = f"""
let s = {{ ticked: new Set(), dug: new Set() }};
const out = [];
for (const [rule, ...args] of {json.dumps(steps)}) {{
  s = R[rule](s, ...args);
  out.push({{ ticked: [...s.ticked].sort(), dug: [...s.dug].sort() }});
}}
console.log(JSON.stringify(out));
"""
    r = node(script)
    return json.loads(r.stdout)


def last(steps: list) -> dict:
    return run(steps)[-1]


def test_unticking_a_lead_stops_digging_it():
    assert last([["dig", "A", True], ["tick", "A", False]]) == {"ticked": [], "dug": []}
    assert last([["tick", "A", True], ["dig", "A", True], ["tick", "A", False], ["tick", "A", True]]) == {"ticked": ["A"], "dug": []}


def test_digging_a_lead_ticks_it_and_undigging_keeps_it_ticked():
    assert last([["dig", "A", True]]) == {"ticked": ["A"], "dug": ["A"]}
    assert last([["dig", "A", True], ["dig", "A", False]]) == {"ticked": ["A"], "dug": []}


def test_unticking_a_card_or_the_page_stops_digging_its_leads():
    steps = [["dig", "A", True], ["dig", "B", True], ["tick", "C", True], ["tickAll", ["A", "C"], False]]
    assert last(steps) == {"ticked": ["B"], "dug": ["B"]}
    assert last(steps + [["tickAll", ["A", "B", "C"], True]]) == {"ticked": ["A", "B", "C"], "dug": ["B"]}


def test_dig_every_lead_ticked_digs_only_the_ticked_ones():
    steps = [["tick", "A", True], ["tick", "B", True], ["digTicked", ["A", "B", "C"], True]]
    assert last(steps) == {"ticked": ["A", "B"], "dug": ["A", "B"]}
    assert last(steps + [["digTicked", ["A"], False]]) == {"ticked": ["A", "B"], "dug": ["B"]}  # one card only


def test_a_state_left_inconsistent_is_settled():
    script = """
const s = R.settle({ ticked: new Set(["A"]), dug: new Set(["A", "B"]) });
console.log(JSON.stringify({ ticked: [...s.ticked], dug: [...s.dug] }));
"""
    r = node(script)
    assert json.loads(r.stdout) == {"ticked": ["A"], "dug": ["A"]}


def test_whatever_the_order_no_lead_is_dug_without_being_ticked():
    """Every sequence of four clicks over two leads: after each one, what is dug is ticked."""
    import itertools

    moves = [["tick", "A", True], ["tick", "A", False], ["dig", "A", True], ["dig", "A", False],
             ["tick", "B", False], ["dig", "B", True], ["tickAll", ["A", "B"], False], ["digTicked", ["A", "B"], True]]
    sequences = list(itertools.product(moves, repeat=3))
    script = f"""
let bad = [];
for (const seq of {json.dumps(sequences)}) {{
  let s = {{ ticked: new Set(), dug: new Set() }};
  for (const [rule, ...args] of seq) {{
    s = R[rule](s, ...args);
    if ([...s.dug].some(l => !s.ticked.has(l))) {{ bad.push(seq); break; }}
  }}
}}
console.log(JSON.stringify(bad.length));
"""
    r = node(script)
    assert json.loads(r.stdout) == 0


def test_the_page_of_a_check_takes_its_rules_from_rules_js():
    check = (RULES.parent / "check.js").read_text(encoding="utf-8")
    assert 'import { LeadRules } from "./rules.js";' in check
    # every change of a box of a lead or of « dig » goes through the rules
    assert "LeadRules.tick(" in check and "LeadRules.dig(" in check and "LeadRules.digTicked(" in check and "LeadRules.tickAll(" in check
