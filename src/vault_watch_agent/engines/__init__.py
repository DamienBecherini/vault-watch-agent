"""The engines of the agent, one module each, built on the contract of `llm.py` (`Engine`, `EngineKind`, `_Journal`):

- `api.py`: the Claude API through the official SDK, billed per token;
- `claude_code.py`: Claude Code of this machine on a Claude subscription, `claude -p` once per call;
- the OpenAI-compatible one is `openai_compat.py`, beside `llm.py` (its path is the one plug-ins and tests know).

Each one declares its `KIND`, which `llm.engines()` lists. Another engine is one more module here with its `KIND`
added there, or a package of its own (docs/write-an-engine.md).
"""

# The contract first: the engines build on it, and `llm` names them in turn. Importing an engine module before `llm`
# would otherwise find `llm` asking for that module while it is half loaded.
from .. import llm  # noqa: F401
