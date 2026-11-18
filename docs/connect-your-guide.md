*[Version française](connect-your-guide.fr.md)*

# Connect your guide

vault-watch-agent keeps a Markdown guide up to date: it reads a watch (what changed in the field), proposes
corrections with their sources, lets you review them, and opens a pull request with the ones you accept. It knows
your guide through one file at its root, `vault-watch.toml`. This page describes that file key by key, what each
optional part unlocks, and how to check that everything is ready.

What a guide needs, at least: Markdown pages in a git repository (the guide is the root of its repository), and a
name and a language in its manifest. Everything else is optional; a missing part switches a step off, it never
makes a run fail.

## In three commands

```bash
vault-watch --guide ../my-guide init      # writes vault-watch.toml from what the folder shows
vault-watch --guide ../my-guide doctor    # what is ready, what is missing (exit code 1 if a run cannot start)
vault-watch --guide ../my-guide serve     # the web interface, on this guide
```

`init` looks at the folder: the GitHub repository of its `origin` remote, its branch, the language of the pages,
the folders that repeat them in another language, the date field of their front matter. It leaves out the tooling
(`node_modules/`, `scripts/`, `docs/`…), the folders whose name starts with `_` (private notes, templates) and the
repository files (`README.md`, `CLAUDE.md`…), and lists the npm scripts of the guide as hints for `[checks]`. Each
guess is commented: read the file before the first run. `--print` shows it without writing it, `--force` replaces
an existing one.

`doctor` checks the manifest, the pages, each mirror, git, `gh` and the repository, the watch, each check and the
program it needs, and the engine (Claude Code signed in with a subscription, or an API key found).

Without `--guide`, the commands take `VAULT_PATH`, then the current folder when it holds a `vault-watch.toml`. The
runs of each guide are kept apart, in a folder of their own under `.vault-watch/guides/`; the settings (engine,
models) are shared by every guide.

## The manifest

The smallest useful one, from the sample guide (`examples/sample-guide/`):

```toml
schema = 1

[guide]
name = "Self-hosted notes server"
description = "running Quillnote, a notes server, and Larkdb, its database, on a machine of your own"

[content]
language = "en"
exclude = ["README.md"]
modified_field = "last_modified"

[watch]
source = "file"
path = "watch.json"
```

A guide that uses every part: [`examples/manifests/ia-on-prem-vault.toml`](../examples/manifests/ia-on-prem-vault.toml).

An unknown key, or a value of the wrong kind, stops the agent with a message that names the key: a typo must not
switch a part off without a word.

### `schema`

`1`, the version of the format. Optional (1 by default).

### `[guide]`

| Key | Required | What it is |
| :-- | :-- | :-- |
| `name` | yes | The guide's name, in the interface and in the prompts. |
| `description` | no | What the guide is about, in one sentence. It goes into the prompts: the model judges relevance against it. |
| `repository` | no | `owner/name` on GitHub. Without it the guide is local: no issue is read, no pull request is opened, the branch of a run stays on your machine. |
| `site` | no | The published site, linked from the interface. |
| `base_branch` | no | The branch runs start from and pull requests target (`main` by default). |

### `[content]`

| Key | Required | What it is |
| :-- | :-- | :-- |
| `language` | yes | The language the pages are written in (`en`, `fr`, `de`…). The prompts ask for corrections in it. |
| `include` | no | Glob patterns of the pages (`["**/*.md", "**/*.mdx"]` by default). `*` stays in one folder, `**` crosses folders. |
| `exclude` | no | Glob patterns left out (`["docs/**", "README.md"]`). Dot folders (`.git`, `.agents`…) are always left out. |
| `mirrors` | no | Translated copies kept in step: `{ en = "en/" }` means `en/<page>` is the English copy of `<page>`. The folder ends with `/`; its pages are not pages of the source language. |
| `modified_field` | no | A front matter date that an accepted correction sets to the day's date (`last_modified`). Without it, the dates of the pages do not change. |

### `[watch]`

Where the items of a watch come from.

| `source` | With | What the agent reads |
| :-- | :-- | :-- |
| `none` (default) | | No watch: the agent verifies the guide and fixes reported errors only. |
| `github-issue` | `label` (`veille` by default), `artifact` (`weekly-watch` by default) | Open issues with that label in `repository`. The body of the issue links the workflow run that collected the watch (`.../actions/runs/<id>`); the items are the `watch.json` of that run's artifact named `artifact`. |
| `file` | `path` | A `watch.json` in the guide, or given on the command line (`vault-watch run --watch-json`). |

A `watch.json` holds the items your collector kept (feeds, release pages, advisories); its format, key by key:
[The watch format](watch-format.md).

```json
{
  "until": "2026-11-02",
  "items": [
    { "title": "Quillnote 5.0 released: Python 3.11 required", "url": "https://example.org/quillnote/releases/5.0",
      "triage": "keep", "date": "2026-10-28", "notes": "The minimum Python version moves to 3.11." },
    { "title": "Larkdb security advisory", "url": "https://example.org/larkdb/advisories/7", "triage": "keep",
      "date": "2026-10-30", "urgent": true, "severity": "High", "notes": "larkdb dump before 2.1..." }
  ]
}
```

Only the items with `"triage": "keep"` are read, urgent ones first. `notes` is what the model reads about the item:
the more facts it holds (versions, dates, figures), the less the model has to guess. `until` is the end of the
watch window, the date of the run's report.

### `[rules]`

Your own instructions for the model, as files of the guide. Without them the agent uses its own, in
[`src/vault_watch_agent/defaults/`](../src/vault_watch_agent/defaults/): read them before writing yours.

| Key | What it governs |
| :-- | :-- |
| `brief` | What a watch item can lead to (nothing, a correction, an addition), which sources count, the size of a correction, severity. |
| `translation_policy` | How a mirror follows the source pages (fidelity, what is never translated, front matter). Used only with `mirrors`. |

### `[checks]`

The guide's own scripts, run by the agent in a copy of the guide. Each one is optional: a check the guide does not
declare reads « not checked » in the report, on the publish screen and in the pull request, never « passed ».
`{out}` in a command is replaced by the path of a JSON file the agent reads afterwards.

| Key | Runs | Expected |
| :-- | :-- | :-- |
| `audits` | before the pull request, on the corrected copy | Exit code 0 when the guide is sound. Its output goes into the pull request when it fails. |
| `claims_due` | at the start of a run (no network) | `{out}`: `{"claimsDue": [{"page": "...", "claim": "...", "recheckBy": "2026-11-01"}]}`, the dated claims whose recheck date has passed. They are listed in the report. |
| `sources` | before the pull request | `{out}`: `{"sources": [{"url": "...", "citations": [{"page": "..."}], "probe": {"status": "ok", "code": 200}}]}`. A source cited by a corrected page whose status is `dead`, `server-error`, `network-error`, `timeout` or `blocked` is listed on the publish screen. |
| `version_floors` | after the corrections are applied | A table `{ script = "...", file = "..." }`: `node <script> --write` updates `file` (the minimum versions the pages state), committed with the corrections. |

### `[budget]`

`max_context_tokens`: a ceiling on what a single model call may read of the guide, whatever the model. The
cross-check, its sweep and the coherence check read the whole guide in one call when it fits in the model's window
(minus a reserve of 100 k tokens for the instructions, the web and the answer) and under this ceiling; otherwise they
run chapter by chapter (one top folder per call, with the pages the corrections change), and the report and the
run view say so: a contradiction between two chapters can then be missed. Not set: the model's window decides.

## What each part unlocks

| Without | The agent |
| :-- | :-- |
| `repository` | works locally: no issue, no pull request, no link to GitHub. |
| `mirrors` | has no translation step and no translation check. |
| `modified_field` | leaves the dates of the pages as they are. |
| `[watch]` | verifies the guide and fixes the errors you report (`vault-watch fix`, « Verify the guide » in the interface). |
| `[rules]` | follows its default brief and translation policy. |
| a check of `[checks]` | says « not checked » where the check would have reported. |

The « Guide » category of the Settings shows the same thing for the guide being served: each part, provided or
missing, and what a missing one switches off.

## The sample guide

`examples/sample-guide/` is a made-up guide of twelve pages with one planted error per check, and its manifest uses
the fewest parts. To try the agent on it, copy it out of this repository (a guide is the root of its own git
repository), then:

```bash
cp -r examples/sample-guide ../sample-guide && cd ../sample-guide
git init -b main && git add . && git commit -m "sample guide"
vault-watch doctor
vault-watch run --watch-json watch.json
```

A run calls the model: with the Claude Code engine it uses your Claude subscription, with the API engine it is
billed to your key (see « Model engine » in the README).
