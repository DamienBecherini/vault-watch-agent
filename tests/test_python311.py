"""The agent supports Python 3.11 (pyproject: requires-python >= 3.11), but is mostly run on 3.12, which accepts
f-strings 3.11 refuses: 0.6.0 broke on 3.11 that way (a backslash in an f-string's expression). Checked here on
the tokens, whatever version runs the tests."""

import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def problems(path: Path) -> list[str]:
    found, stack = [], []  # stack: the quote of each enclosing f-string
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.FSTRING_START:
                quote = tok.string.lstrip("rRfFbB")[0]
                if stack and stack[-1] == quote:
                    found.append(f"{path.name}:{tok.start[0]}: nested f-string with the same quote")
                stack.append(quote)
            elif tok.type == tokenize.FSTRING_END:
                stack.pop()
            elif stack and tok.type != tokenize.FSTRING_MIDDLE:
                if tok.type == tokenize.COMMENT:
                    found.append(f"{path.name}:{tok.start[0]}: comment in an f-string")
                elif "\\" in tok.string:
                    found.append(f"{path.name}:{tok.start[0]}: backslash in an f-string expression")
                elif tok.type == tokenize.STRING and tok.string.lstrip("rRbBuU")[:1] == stack[-1]:
                    found.append(f"{path.name}:{tok.start[0]}: same quote in an f-string expression")
    return found


@pytest.mark.skipif(sys.version_info < (3, 12), reason="3.11 compiles the code itself")
def test_no_f_string_that_python_3_11_refuses():
    files = [p for d in ("src", "tests", "examples") for p in (ROOT / d).rglob("*.py")]
    assert [p for f in files for p in problems(f)] == []
