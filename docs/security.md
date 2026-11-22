*[Version française](fr/security.md)*

# Security

What the agent can reach, what the model can do, and what to know before connecting a guide. In short: the
model only answers in a fixed shape, the code decides what is written, a human reviews before anything leaves the
machine, and keys are never stored by the agent.

## Keys and tokens are references

The agent never stores a key. Every field that needs one takes a reference to where it lives:

| Reference | Where the value is |
| :-- | :-- |
| `env:NAME` | an environment variable (set by your shell, or injected by `sops exec-env`) |
| `sops:file#NAME` | a field of a file encrypted with [sops](https://github.com/getsops/sops), decrypted when a call needs it |
| `file:path` | a file that holds the value alone |

This holds for the API key of the settings (`key`), the OpenAI-compatible server's key, and the token of a Gitea
forge (`[guide] forge_token`). A value in plain text is refused when the settings are saved and again when they
are read. The value is read at the moment of a call and is never written to the journal, the reports or the
messages. GitHub goes through `gh`, signed in by you (`gh auth login`): the agent never sees its token.

A Gitea token is valid on every repository its account can reach (Gitea has no per-repository token): give the
agent an account of its own, collaborator of the guide's repository alone, with the `repository` scope (and
`issue` for an `issues` watch).

## What the model can do

- **Answer, not act.** Every call answers into a Pydantic schema (structured output). The model has no tool that
  writes a file, runs a command or calls git. The only tools it gets are web search and page reading, on the
  steps that check sources.
- **A correction is a quote and a replacement.** The code applies it only when the quoted text occurs exactly once
  in the page (`vault.check`), on a git worktree of a new branch, never on `main`. A read-only page
  (`[content] readonly`) is refused whatever step proposes the edit.
- **A correction touches only a page of the guide.** The page a correction names is written by the model, from
  what it read; the code accepts only a content page of the guide or its mirror (`vault.is_page`: a relative path
  inside the guide, a Markdown page of `[content] include`). Never the guide's scripts, its manifest, a dot folder
  or a file outside the guide: the agent runs the guide's checks after applying, so a correction on one of them
  would have been code run on your machine (until 1.4.2).
- **Two human pauses.** Nothing is applied before the review, nothing is pushed before a second yes. The pull
  request is then merged by a human, on the forge.
- **Claude Code runs bare.** On the `claude-code` engine each call is `claude -p --safe-mode` with none of your
  instructions, hooks, skills or MCP servers, no conversation kept, no tool at all on the steps that do not check
  sources, and the API keys removed from its environment. On the steps that check sources it gets its WebSearch
  and, in place of its WebFetch (which runs on your machine and read any address, your local network included),
  the agent's own page reader as a local MCP tool (`mcp_fetch.py`); those calls load no setting source instead of
  `--safe-mode`, which would turn that tool off too: your settings, hooks, plugins and instructions stay out all the
  same. It is refused when it is signed in otherwise than with a subscription, so that a call is never billed
  without a question.

## What the model reads is data

The watch (release notes, advisories, feeds) and the pages read on the web are written by others. A page may
contain text written to steer a model. The agent does not rely on the model resisting it; it limits what such
text can achieve:

- the worst it can do is make the model propose a wrong correction or a wrong verdict. Each proposal shows its
  source and a word-level diff in the review, and the cross-check reads it again with the whole guide;
- a passage the model says it found is looked up in the page by the code (`quotes.py`): a quote that is not there
  is shown as such, never as the guide's text;
- the agent's page reader (`webtools.py`: for the OpenAI-compatible engine, for Claude Code through `mcp_fetch.py`,
  for the links read whole and the notes of a watch) reads http and https only, and refuses any address that is not
  public: not the machine itself, the local network, or a cloud metadata address. It checks the address each
  request actually reached, not only the one the name gave when checked (DNS rebinding), each redirection, and an
  IPv6 address that carries a private IPv4 one (NAT64, 6to4, Teredo). The Claude API's web tools run on Anthropic's
  servers and cannot reach your network;
- a link the page shows is a link only when it is an http(s) address (never `javascript:`), whoever wrote it: a
  model, a feed, a page;
- the model's answers never become commands: the only programs the agent runs are git, `gh`, the guide's own
  checks and, when your settings use them, `claude` and `sops`, with arguments built by the code.

## What leaves the machine

There is no telemetry: the agent sends nothing about you or your guide to its author. It uses the network for:

| What | To whom |
| :-- | :-- |
| The model calls: the instructions, the watch, the pages or the whole guide | The engine you chose |
| Web search and page reading, on the steps that check sources | The engine's own web tools, or your SearXNG and the pages themselves |
| The collection of a watch and the check of its sources | GitHub, Hugging Face, the feeds and the pages of `feeds.json` |
| The links of the pages, when they are checked | The sites the guide links to |
| Issues, artifacts, the branch and the pull request | The guide's forge: GitHub through `gh`, or your Gitea |
| The public price list, when you ask for it in the Settings | A file of the LiteLLM repository, on GitHub |

« Give my opinion » sends nothing by itself. It prepares a GitHub issue or an e-mail that you read and send
yourself, or a text to copy. The version is in it; the system, Python, the engine and the screen are added only
when you tick the box; nothing of the guide ever is, not its name, its pages or the run on the screen.

## The local server

`vault-watch serve` listens on 127.0.0.1 only. It refuses a request whose `Host` header is not local (DNS
rebinding) and a request the browser marks as coming from another site (`Sec-Fetch-Site`, `Origin`). Every call of
its API, a read included, must carry an `X-Vault-Watch` header, which a page of another site cannot send without a
CORS preflight the server never grants; only what the browser asks by itself goes without it (the health probe,
the notices, a run's stream, its report). Until 1.4.2 a read needed no header, and an image on any site could make
the server resolve a key and send it away. The page is never shown in a frame of another site (`X-Frame-Options`,
`frame-ancestors`), runs only its own scripts (a Content Security Policy) and is never sniffed. There is no account:
anyone who can open a connection on the machine itself can use it, so do not expose the port (a reverse proxy, a
tunnel) without an authentication in front.

## Before connecting a guide

- **The manifest runs commands.** `[checks] audits`, `claims_due`, `sources` and `version_floors` are commands the
  agent runs in the guide's folder, as you. Connect only a guide whose manifest you have read, as you would
  before running its `npm test`.
- **The guide is sent to the model.** A cross-check sends the whole guide (minus `exclude`) to the engine you
  chose: Anthropic for `api` and `claude-code`, your server for `openai`. Leave out with `exclude` the pages that
  must not leave the machine, or use a local model.
- **The cost journal** (`~/.vault-watch/usage.jsonl`, or `VAULT_WATCH_JOURNAL`)
  holds run names, steps, models, tokens and costs, no content of the guide. This repository versions the one of
  the reference guide; keep yours out of a public repository if the run names say too much.

## Reporting a problem

Report it privately from the Security tab of the GitHub repository (« Report a vulnerability »), not in a public
issue.
