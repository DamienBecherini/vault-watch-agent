"""Which translated passage goes beside which passage of the source (static/pairs.js, run with node): a passage the
translator left alone gets an empty cell, and the passages after it stay beside their own translation (seen on a demo:
every row after it showed the translation of the next passage). Skipped where node is not installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PAIRS = Path(__file__).parent.parent / "src" / "vault_watch_agent" / "static" / "pairs.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")


def rows(source: list, target: list) -> list:
    """alignPairs(source, target) as [source's new text or None, target's new text or None, t]."""
    module = (f"{PAIRS.read_text(encoding='utf-8')}\n"
              f"console.log(JSON.stringify(alignPairs({json.dumps(source)}, {json.dumps(target)})"
              ".map(r => [r.source && r.source[1], r.target && r.target[1], r.t])));")
    r = subprocess.run([NODE, "--input-type=module", "-"], input=module, capture_output=True, text=True,
                       encoding="utf-8", check=True)
    return json.loads(r.stdout)


SOURCE = [
    ["Ollama reste le plus simple pour démarrer.", "Ollama reste le plus simple pour démarrer sur un poste seul."],
    ["La version 0.31 de vLLM est le minimum.", "La version 0.33 de vLLM est le minimum (avis GHSA-2025-x)."],
    ["Voir [le guide](https://example.org/a).", "Voir [le guide](https://example.org/b)."],
]
TARGET = [
    ["Ollama remains the simplest to start.", "Ollama remains the simplest to start on a single machine."],
    ["vLLM 0.31 is the minimum.", "vLLM 0.33 is the minimum (advisory GHSA-2025-x)."],
    ["See [the guide](https://example.org/a).", "See [the guide](https://example.org/b)."],
]


def test_each_passage_beside_its_own_translation():
    assert rows(SOURCE, TARGET) == [[s[1], t[1], i] for i, (s, t) in enumerate(zip(SOURCE, TARGET))]


def test_a_passage_without_translation_gets_an_empty_cell_and_shifts_nothing():
    for missing in range(3):
        target = [t for i, t in enumerate(TARGET) if i != missing]
        got = rows(SOURCE, target)
        assert [r[0] for r in got] == [s[1] for s in SOURCE]
        assert got[missing][1:] == [None, -1]
        kept = [r for i, r in enumerate(got) if i != missing]
        # each translation beside its own passage, with its rank in the mirror's list (the key of its retouch)
        assert [r[1:] for r in kept] == [[t[1], i] for i, t in enumerate(target)]


def test_an_edit_without_its_passage_gets_a_row_of_its_own():
    extra = ["", "A footnote the translator added: [^1]: https://example.org/note"]
    got = rows(SOURCE[:2], [TARGET[0], extra, TARGET[1]])
    assert got == [[SOURCE[0][1], TARGET[0][1], 0], [None, extra[1], 1], [SOURCE[1][1], TARGET[1][1], 2]]


def test_a_removed_passage_goes_with_a_removed_translation_only():
    source = [["Un paragraphe obsolète sur la 0.30.", ""], SOURCE[1]]
    assert rows(source, [TARGET[1]]) == [[source[0][1], None, -1], [SOURCE[1][1], TARGET[1][1], 0]]
    assert rows(source, [["An outdated paragraph about 0.30.", ""], TARGET[1]]) == [
        ["", "", 0], [SOURCE[1][1], TARGET[1][1], 1]]


def test_nothing_on_either_side():
    assert rows([], []) == []
    assert rows(SOURCE[:1], []) == [[SOURCE[0][1], None, -1]]
    assert rows([], TARGET[:1]) == [[None, TARGET[0][1], 0]]
