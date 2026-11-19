*[Version française](compatibility.fr.md)*

# What stays stable

From 1.0, four formats are frozen. Each carries a version number, and the agent refuses a number it does not know
with a message that says what to update. A change to one of them is a new number, never a silent change of meaning.

| Format | Where | Number | Written by |
| :-- | :-- | :-- | :-- |
| The manifest of a guide | `vault-watch.toml` at the root of the guide | `schema = 1` | you ([connect-your-guide.md](connect-your-guide.md)) |
| A watch | `watch.json` | `"schema": 1` | your collector or `vault-watch collect` ([watch-format.md](watch-format.md)) |
| The engine protocol | `llm.Engine`, `llm.EngineKind` | `EngineKind.protocol = 1` | an engine package ([write-an-engine.md](write-an-engine.md)) |
| The settings | `.vault-watch/settings.json` | `"schema": 1` | the Settings page, or you |

## The rules

- **Within a number, only additions.** A new optional key, a new watch source, a new optional field of an item: a
  file that was valid stays valid and means the same. A key is never removed or given another meaning without a
  new number.
- **A file newer than the agent is refused**, not half read: `schema 2 … update vault-watch-agent`. An older agent
  would otherwise drop what it does not know, and for the settings it would save the file without it.
- **A file older than the agent is migrated.** The settings are migrated when they are read, one number at a time,
  and written back in the current format on the next save. For the manifest and the watch, a new number comes
  with its migration in the release notes, and the agent keeps reading the previous number for one major version.
- **The engine protocol is checked when the engine loads.** An engine package that implements another protocol is
  not loaded: the Settings page lists it with the reason, and the other engines keep working.
- **Names of before 1.0 stay readable.** `source = "github-issue"` is read as `issues` (the source also reads the
  issues of a Gitea forge); a settings file without `schema` is read as schema 1.

## What is not frozen

The working files of the agent (`checkpoints.sqlite`, the journal of runs, the reports of a check, the files of
`.vault-watch/<guide>/`) belong to the agent: a version may change them, and says so in its release notes. The
prompts, the steps of a run and the web interface change with each version. The Python modules are not a library:
only `llm.Engine` and `llm.EngineKind`, for engine packages, are part of the protocol.
