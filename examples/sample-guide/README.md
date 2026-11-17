# Sample guide

A made-up guide (Quillnote, a notes server, and Larkdb, its database) for the tests and for trying the agent without
the IA on-prem vault. Twelve pages in three chapters, English only, no mirror, no script of its own.

Planted errors, one per check, so a run has something to find:

| Check | Where | What |
| :-- | :-- | :-- |
| Stale version (the watch) | `02-install/requirements.md` | Python 3.9; item 1 of `watch.json` says Quillnote 5.0 needs 3.11 |
| Contradiction between pages (consistency) | `01-basics/architecture.md`, `02-install/configuration.md` | Larkdb port 7300 against 7400 (item 2 says 7300) |
| Dead link | `02-install/install-linux.md` | `https://example.invalid/...` never answers |
| Advisory to report | `03-operate/backups.md` | item 3: `larkdb dump` before 2.1 |

`watch.json` holds eight items: five kept by the collector (one urgent), three dropped.

The tests copy this folder into a temporary git repository (`tests/conftest.py`, fixture `sample_guide`). Until the
optional parts of milestone M1 land, the fixture adds what the agent still requires of a guide (a stub
`scripts/audit-freshness.mjs`); see [phase G of ROADMAP.md](../../ROADMAP.md#phase-g--a-modular-agent).
