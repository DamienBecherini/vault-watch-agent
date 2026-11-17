# Contributing

## Set up

Python 3.11 or later, git, and Node.js (the agent runs the guide's own scripts). Claude Code or an Anthropic API key
only to run the agent for real; the tests need neither.

```bash
git clone https://github.com/DamienBecherini/vault-watch-agent
cd vault-watch-agent
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv/Scripts/pip
.venv/bin/python -m pytest -q
```

## Tests

- No test calls a model or the network: the graph runs with a fake model (`FakeLLM` in `tests/test_graph.py`,
  `SampleLLM` in `tests/test_sample_guide.py`).
- `examples/sample-guide/` is a small made-up guide with planted errors; the fixture `sample_guide`
  (`tests/conftest.py`) copies it into a throwaway git repository. Prefer it for a new test of the graph.
- CI runs the suite on Linux and Windows, Python 3.11 and 3.12. Paths and subprocesses differ between the two: test
  on both when you touch them.

## Proposing a change

1. Open an issue first for anything larger than a fix (a new engine, a new kind of guide, a new step).
2. One change per pull request, with its test.
3. Commit messages: one line saying what changes and why, in plain English; details in the body if needed.
4. Update `CHANGELOG.md` (section "Unreleased") and the docs a user would read (`README.md`, `docs/`).

Where the project is going: [ROADMAP.md](ROADMAP.md) and [docs/modular-plan.md](docs/modular-plan.md).

## Secrets

Never commit a key. The settings take a reference to it (`env:NAME`, `file:path`, `sops:file#NAME`), never the key
itself, and the tests use fake values.
