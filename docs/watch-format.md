*[Version française](watch-format.fr.md)*

# The watch format (`watch.json`)

A watch is what changed in the field of a guide over a window of days: releases, security advisories, new models,
news. A collector gathers it (the IA on-prem guide's `watch-feeds.mjs`, the agent's own `vault-watch collect`, or
anything you write) and hands it to the agent as one `watch.json`. This page is the contract between the two.

```json
{
  "schema": 1,
  "since": "2026-11-08",
  "until": "2026-11-16",
  "items": [
    {
      "title": "vllm-project/vllm v0.33.1",
      "url": "https://github.com/vllm-project/vllm/releases/tag/v0.33.1",
      "date": "2026-11-12T09:30:00Z",
      "triage": "keep",
      "reason": "release of a tool the guide covers",
      "urgent": false,
      "feed": "vllm", "domain": "engines", "tier": "A",
      "notes": "Release notes, cached by the collector: what the model reads about the item."
    }
  ],
  "errors": []
}
```

## The file

| Key | Required | What it is |
| :-- | :-- | :-- |
| `schema` | no | The version of this format, `1` today (absent: 1). The agent refuses a file whose `schema` is newer than the one it reads, and says which: update the agent. |
| `since`, `until` | `until` | The window, as dates (`YYYY-MM-DD`). `until` is the date of the run's report and of its branch. |
| `items` | yes | The items, kept or dropped (below). |
| `errors` | no | What the collector could not read (a feed down, a rate limit), one string each; shown, never fatal. |

Other keys (counts, the collector's version) are allowed and ignored.

## An item

| Key | Required | What it is |
| :-- | :-- | :-- |
| `title` | yes | One line: what happened. |
| `url` | expected | The primary source: the release page, the advisory, the announcement. The model opens it to check a fact; without it, it can only take the notes at their word. |
| `date` | expected | When it happened, ISO 8601 (a date or a date and time); the agent keeps the date, and a correction states the fact with it. |
| `triage` | yes | `keep` or `drop`: the collector's own sorting, by rule (a pre-release, a routine patch, a feed out of scope). Only `keep` items reach the model. |
| `reason` | no | Why the collector kept or dropped it, one line. |
| `urgent` | no | `true` for a security advisory to handle before the others: they come first in the run. |
| `severity` | no | The advisory's own severity (`Critical`, `High`…), as the source gives it. |
| `notes` | no | What the model reads about the item: the release notes, the advisory's text, cached when the watch was collected. The more facts they hold (versions, dates, figures), the less the model guesses. Cut at 4,000 characters. `summary` is read when there are no `notes`. |
| `feed`, `domain` | no | Which feed and which part of the guide the item comes from; shown in the report. |
| `tier` | no | How far the source can be trusted: `A` primary (release notes, the vendor's page, the advisory), `B` reputable secondary, `C` a lead only. |

Unknown keys are kept in the file and ignored by the agent.

## How the agent reads it

The kept items get a run-local id (`W1`, `W2`…), urgent ones first, and go to triage: for each, the model says
whether it makes a page of the guide wrong (a correction), could add to it (a lead for the editor), or changes
nothing; what the model drops is listed at the end of the report with its reason. The items the collector
dropped are not read.

## Where it comes from

The guide's manifest says it (`[watch]`, see [Connect your guide](connect-your-guide.md)): a `watch.json` in the guide
(`source = "file"`), the artifact of the workflow run linked from a GitHub issue (`source = "github-issue"`), or none.
