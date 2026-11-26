# Changelog

Versions follow the milestones of [phase G of ROADMAP.md](ROADMAP.md#phase-g--a-modular-agent). The version is written
once, in `src/vault_watch_agent/__init__.py`; `/api/health`, `/api/info` and the page footer show it.

## Unreleased

- **An advisory the guide answers another way no longer comes back** (noticed on the guide's watch #110, 2026-11-25:
  LiteLLM's 1.106 line, kept with two workarounds, raised three advisories fixed only from 1.108.0 at every urgent
  watch): the floors file takes `answered`, {advisory id: {page, why}}; the collection drops them (« answered by the
  guide (page) »), and « Check the sources » lists them, flagging a page gone or that no longer names the advisory.
- **No test reaches the network** (asked by the user, 2026-11-26, after the CI of 1.7.0): the fixture `no_network`
  refuses any connection outside the machine and makes `gh` answer as on the CI, signed in nowhere
  (`tests/test_offline.py`). A test of the publish pause that failed once in the whole suite now says the job's
  error.

## 1.7.1 (2026-11-26)

The CI green again: tests of 1.7.0 passed only on the machine they were written on (one needed `gh` signed in, the
others a checkout with `\n` line endings). Nothing changes in what the agent does.

- **Fixed: a test reached GitHub** (`test_a_watch_run_notes_what_it_sets_aside_once_the_registry_is_used`): a watch
  run of « issue #30 » fetched the real issue and its artifact through `gh`; the CI has no `gh` signed in. The test
  now gives the run its own watch.
- **Fixed: the tests of the screen « Candidates » failed on Windows**: they edited the sample manifest looking for
  `\n`, and a Windows checkout has `\r\n` (nothing changed, nothing to commit). They read it in text mode now;
  tried on a sample guide converted to CRLF.

## 1.7.0 (2026-11-26)

Discovery: what the guide does not cover yet is followed over time in a registry of the guide (`[watch] candidates`),
seen and changed on the screen « Candidates », fed by the watch runs and the checks, and read on Hugging Face and
GitHub when the guide names these readers (`[watch] candidate_readers`). Also: the runs named with their time, a
footnote that stays with no citation fixed, a page opened before an update that says so, the editor's journeys
clicked in Chrome, a report at the end of each test suite. A guide whose manifest uses the new keys
(`candidates`, `candidate_kinds`, `candidate_readers`) needs 1.7.0 wherever it is read (its collection included).

- **The registry of discovery** (ROADMAP D3.1, decided with the user on 2026-11-25): `candidates.py` follows over time
  what the agent found and the guide does not cover yet, in a JSON file of the guide the manifest names
  (`[watch] candidates`, created when first saved): each candidate has a name, a kind (model, tool, hardware, other),
  a state (`lead`, `watching`, `confirmed`, `proposed`, `added`, `dismissed`: a reason needed), a date to look again
  (for `watching` and `dismissed`, after today), its sources (address, date, where it came from) and its history;
  names and addresses are matched in one form. The collection drops the addresses it tracks (« already seen ») and
  lists the candidates due in the watch (`recheck`) and its issue (« Candidates to look at again »).
- **The screen « Candidates »** (ROADMAP D3.2, in the menu « Watch »): the registry by state, the candidates due
  flagged; add one by hand (a name or an address already known adds its source), watch or dismiss it (a reason,
  needed to dismiss, and a date to look again), confirm it, mark it added, propose it as an addition (« Propose an
  addition » opens with its line, and the run started marks it `proposed`, naming the run). The changes stay in a
  draft of the agent, never in the guide's folder; « Publish the registry » writes it on a branch of the guide and
  opens the pull request, which adds `[watch] candidates` to the manifest when it is missing (the path asked, beside
  the watch's files by default; it needs vault-watch-agent 1.7.0 wherever the guide is read). While it is open,
  publishing again adds a commit to it; merged, the folder follows and the draft goes.
- **What a candidate is, read without a model** (ROADMAP D1): `enrich.py` reads a Hugging Face model page through
  Hugging Face's public API (licence, parameters, context from its `config.json`, GGUF, downloads, dates) and a GitHub
  repository through GitHub's (licence, stars, latest release, contributors up to « 100+ », last push, archived),
  when a candidate is added by hand or by a watch run, and on « Read again » on its card. Kept in the candidate
  (`facts`, with the day read) and shown on the page; a failure is said and keeps what was read before.
- **The readers of candidates are the guide's** (asked by the user, 2026-11-26: Hugging Face and GitHub fit a guide
  of AI or software, not every guide): `[watch] candidate_readers` in the manifest names where candidates are read
  (`"huggingface"`, `"github"`), **none when not given**: a guide that names none sends nothing to these sites, and
  the kind of a candidate is no longer guessed from such an address. One reader per site in `enrich.py` (`READERS`),
  so that another one is an entry there; what a reader dropped since had read stays; « Read again » shows only on a
  candidate the guide's readers can read.
- **Where the candidates come from** (ROADMAP D3.3): once the guide uses the registry (its manifest names it, or a
  draft was started on the page), the possible additions a watch run sets aside become leads (the item's address,
  the watch, the reason) instead of a line of its report; a lead of an addition check that the editor dismisses
  becomes a dismissed candidate (not a lead « Newer »), so that it does not come back. The kind is guessed from the
  address (a Hugging Face model page, a GitHub repository). The draft moved into `candidates.py`, shared by the page,
  the runs and the checks.
- **The kinds of candidates are the guide's** (asked by the user, 2026-11-25: they depend on the guide):
  `[watch] candidate_kinds` in the manifest, `["model", "tool", "hardware"]` when not given, « other » always added;
  the registry refuses a kind the guide does not declare (a candidate keeps a kind removed since), the page offers
  the guide's and shows a kind it does not translate as it is written.

- **The editor's journeys clicked in a real browser** (asked by the user, 2026-11-22 and 2026-11-25):
  `tests/test_e2e.py`, six journeys Playwright clicks in Chrome on the throwaway guide and the fake model: review
  and apply (a group ticked by its own box, nothing ticked: nothing to apply), skip the retouches and decline to
  publish, with the publish checklist read; a correction retouched at the review is what is applied; a page corrected
  at the publish pause is committed and checked again; a lead ticked on a check becomes an addition run named with
  its time; a candidate added, dismissed with its reason, then proposed; the Settings open and close, the language switches. Marked `e2e`, left out of a plain `pytest`
  (`pytest -m e2e`), the extra `e2e` (`playwright`, `uvicorn`), no browser download: the Chrome of the machine, or
  `$VW_CHROME`. About 15 seconds: a CI job `e2e` of its own, on Linux.

- **The runs named with their time** (asked by the user, 2026-11-25: two addition runs of the same day were
  `add-2026-11-25` and `add-2026-11-25-2`): a fix, addition, compaction or « Languages » run started from the page or
  with `vault-watch mirror` is now `<kind>-YYYY-MM-DD-HHMM`, local time (`add-2026-11-25-2130`), like the checks;
  a second one in the same minute still gets `-2`. The runs already made keep their names.
- **Fixed: a footnote could stay with no sentence citing it** (found by the user, 2026-11-25: `[^22]` and `[^23]` of
  the IA guide's security page, left by the compaction of 2026-11-20). `compact.with_orphan_notes` removes a note
  with the trim that orphans it, but sees one group at a time: two trims of two groups that each removed one citation
  left the note. Now the apply step, after all the accepted corrections of a page, whatever the run (fix, watch,
  addition, compaction), removes the definition of each note whose last citation they removed (with its indented
  lines; a note already uncited before the run is left as it was), and the pull request names them
  (`vault.drop_orphan_notes`). « Before publishing » gets a line « Footnotes »: in the changed pages and their
  mirrors, a note no sentence cites, one cited and never defined, one defined twice (code aside), to fix with
  « Correct »; the pull request says them too (`graph_publish.footnote_problems`). A note cited before a colon
  (« approximate rule[^1]: ») is a citation: only `[^n]:` at the start of a line defines one (`vault.note_calls`;
  before, such a note was said never cited, and the apply step could have removed its definition).
- **A page opened before the server was updated says so** (found at the publish pause of 2026-11-25: a tab opened
  earlier lacked the line « Footnotes »): each answer of the API carries the version of the page
  (`X-Vault-Watch-Page`), the page compares it with the one it was served with and offers to reload.
- **Each test suite ends with a report** (asked by the user, 2026-11-25, to spot a test that fails once in a while):
  `.pytest-report.md`, not versioned (what failed with the first line of its error, the slowest tests, « failed
  before, passed now »), and the history of the last 50 suites (`.pytest-history.jsonl`); `tests/report.py`.

## 1.6.1 (2026-11-25)

The CI green again: its job `lint` checks the types as Linux sees them. Nothing changes in what the agent does.

- **Fixed: the CI's job `lint` failed on Linux** (1.6.0's tests passed everywhere): pyright did not find `pypdf`,
  optional and not installed there (the job now installs the extra `pdf`), and found `subprocess.CREATE_NO_WINDOW`
  unknown off Windows (`notify.py` reads it with `getattr`, in a function only Windows calls). Pyright had been run
  on Windows only; `--pythonplatform Linux` checks as CI does.

## 1.6.0 (2026-11-25)

The code split by area and checked by ruff, pyright and TypeScript, with nothing changed in what it does; dl-sub-dub
started by the agent when a video is to be read, its own protections and limits said; any guide taken for itself:
a folder without a manifest is no longer read as the IA on-prem guide, and the page no longer assumes a French guide
with an English mirror. 385 tests, the 11 screens drawn in a real browser without an error.

- **dl-sub-dub started when a video is to be read** (asked by the user, 2026-11-25: the agent waited for it to be
  started by hand): the command of `videos.start`, set by hand in `settings.json` only (the page can no longer change
  it, since the agent runs it), without a shell, its port the one of `videos.url` when it names none, in its own
  folder, without the agent's keys and tokens, detached; it stops by itself after its own time without activity. The
  tab « Links to read whole » says it is stopped and will be started (`videos.py`). When the program of
  `videos.start` is not there (dl-sub-dub not installed), the tab says so, with where to get it. dl-sub-dub's own
  protections are said: a second dl-sub-dub refused because another one runs for the same data (its exit code 4, its
  message naming that one's address, said at once instead of after 90 s), and a video ended by `gpu_busy` (the
  graphics card taken by another program, its free memory): read the link again later. A video over dl-sub-dub's
  limit (the estimated transcription work since its `max_work_min`, no longer the length) is said in minutes, with
  where to raise it.
- **Fixed: a folder without `vault-watch.toml` was taken for the IA on-prem guide**, the guide the agent was written
  for: its repository, its site and its Node scripts, on anyone's machine. Only that guide is now read without a
  manifest (by its watch brief and its audits script); any other folder is refused with what to do (`vault-watch
  init`, then `doctor`), and `doctor` run from a folder of a guide says where its root is (asked by the user,
  2026-11-25: nothing of the author's machine assumed elsewhere).
- **Fixed: the page took every guide for a French one with an English mirror.** The passages, the diffs and the
  boxes to edit were marked `lang="fr"` or `lang="en"` (a path under `en/` was English, anything else French): the
  browser's spellcheck, hyphenation and screen readers then used the wrong language on another guide. The server now
  puts the guide's languages in the page (`<meta name="vault-watch-guide">`: its source language, each mirror's
  folder) and `util.js` (`langOf`) gives each passage the language of its page. The texts that said « French » and
  « English » for the source and its translation (« English translation », « English pages updated », « you
  corrected the French ») now say « source » and « translation ». Found by the test that looks for the IA on-prem
  guide's strings in the code, which read only the top-level modules: it now reads `routes/`, `engines/` and the
  page too, as does the test that every model call names its step.
- **The code split by area and checked by ruff, pyright and TypeScript (1.6.0 quality pass); what it does is
  unchanged.** `web.py` (1,886 lines) is now 83: `create_app` builds the app from one router per area of the page, in
  the new package `routes/` (`context.py` holds what they share, `AppContext`; `security.py` the local-only middleware
  and the headers of every answer). `graph.py` (1,058 lines) is now 94: `build` binds nodes written as functions
  `node(deps, state)` with `functools.partial`, in `graph_proposals.py`, `graph_review.py` and `graph_publish.py`, with
  `graph_corrections.py`, `graph_text.py` and `graph_common.py` beside them; no node is a closure of `build` any more.
  `llm.py` (679 lines) is now 442 and keeps the contract: the `LLM` and `Engine` protocols (which now name `web`,
  `for_step`, `run`, `kind` and `prices`), `ModelError`, `Capabilities`, `_Journal`, `EngineKind`, `create`; each
  engine has its own module with its `KIND`: `engines/api.py`, `engines/claude_code.py`, and `openai_compat.py` where
  it was. The old names are still imported from `web`, `graph` and `llm`. The page's `app.js` (3,420 lines) is split
  into ES modules by area (31 scripts in all), each with `// @ts-check`; `index.html` loads `app.js` as a module, which
  imports the others, and `boot.js` stays a classic script before the first paint. Nothing is built: the files are
  served as they are, with `Cache-Control: no-cache`. ruff (its rules in `[tool.ruff]`, lines of 160) and pyright
  (basic, `[tool.pyright]`) are clean on all of `src`; CI runs them in a job `lint`, and TypeScript on the page
  (`jsconfig.json`, `types/page.d.ts`) in a job `page`; `pip install -e ".[dev]"` brings ruff and pyright. Checked:
  the same 61 routes before and after, their answers compared; the compiled graph identical; the 384 tests passing.
  [How the code fits together](docs/code.md) maps the new modules, with the commands to run the checks locally.
- **Fixed: a passage of the source without a translation shifted every row after it**, at the translation pause of
  a « Sync the languages » run and on the publish screen. The passages that changed in a source page and the
  translator's edits of its mirror were paired by their rank: after a passage the translator left alone (the mirror
  already said it, or its edit could not be placed), each row showed a source beside the translation of another
  passage. `static/pairs.js` (`alignPairs`) now puts each edit beside the passage it translates, judged by what a
  translation keeps (numbers, links, code, names); a passage without one says « Nothing translated for this passage »
  (`tests/test_pairs.py`, run with node). `tests/test_rules.py` now runs `rules.js` as the ES module it is.

## 1.5.0 (2026-11-25)

What you write during a run, proofread when you ask; the explanations of every pause in the page's language;
desktop notifications on macOS and Linux; a new welcome in the README with two diagrams. Tried for real on the IA
on-prem guide, on the Claude subscription: an error reported (PR #111: a figure added by hand with no source found
and removed, a translation written by hand kept by the loop) and the urgent watch #110 (PR #112).

- **The explanations of the pauses in the page's language** (asked by the user after the first real run proofread
  on 2026-11-25: the reasons and the doubts were in English in the French page): why a correction is proposed, the
  cross-check's verdict, the warning of the free checks, the reason of a fix and the doubts of a proofreading (of a
  run or of the page « Languages »), what the translator and the links check said, the run's title. The checks keep
  writing them in English (the report and the pull request quote them); the page asks `/api/explain` when it shows
  them in another language: one call of the translation model at low effort (the step `explain`, set apart like
  any other) for the lines not translated yet, kept in `explained/<language>.json` of the run's working folder; the
  English on hover; a model that fails leaves the English (`explain.py`, `tests/test_explain.py`). A screenshot of
  « Your edits proofread » in [A run](docs/run.md#have-your-edits-proofread), in both languages.
- The boxes where a text is changed before it is applied (a fix of a proofreading, a translation at its pause, a
  retouched correction) stand out: framed in the accent colour, « ✏️ This text will be applied: you can change it
  here » above them (the box read as a third diff). The pull request says where each proofreading was asked (at the
  retouches, before publishing). The engines and models of « Engine and models of this run » said in the page's
  language (« Claude Code · Opus 5.5 · high effort · subscription »).
- The page in French no longer names the author's own launcher when the server is gone: « the server does not
  answer, it may have stopped after being idle (`serve --idle-exit`); start it again », as in English.
- **What you write during a run, proofread when you ask** (proposed by the user: only the translation and the
  guide's checks ran again on an edit by hand, never a check of its facts): at the retouch pause, « I am done » can
  ask for the three checks of the page « Languages » (spelling, facts on the web, consistency with the whole guide)
  on what was changed by hand since the corrections were applied, never on the corrections of the run; at the publish
  step, a source page corrected can be proofread the same way, then translated and checked again. The run stops on
  the fixes found (a new pause, `proofread_review`, after the node `proofread` that calls the models, so that they
  are called once), each to tick, retouch or leave; those accepted are committed as the editor's, and the pull
  request says what was proofread. Nothing asked, or nothing found: no call, no pause. On the command line:
  `resume --retouch done --proofread spelling,facts`, then `resume --accept F1`.
- **Desktop notifications on macOS and Linux too** (`serve --notify`, Windows only before): `terminal-notifier` on
  macOS when it is installed (a click opens the page), else `osascript`; `notify-send` on Linux, with a button that
  opens the page when it supports actions. The title and the text go as arguments, never into a script. Without a
  notifier, nothing is shown and the run goes on, as before. The README says how `pipx` installs the command.
- **Security: Claude Code reads pages through the agent's reader** (the rest of the audit of 2026-11-22 was published in 1.4.2): its own WebFetch runs on the editor's machine and read
  any address, the machine and its local network included (measured: it connected to 127.0.0.1 and to the PC's LAN
  address). On the steps that use the web, Claude Code now gets the agent's page reader as a local MCP tool
  (`mcp_fetch.py`, `web_fetch`: public addresses only, the one connected to as well, redirections checked) in place
  of WebFetch, which is denied; its WebSearch stays. Those calls load no setting source of the user instead of
  `--safe-mode` (which also turns the agent's MCP server off): the user's settings, hooks, plugins and instructions
  stay out all the same (checked with a real call).
- **pypdf ≥ 6.1** for the PDFs of the links read whole.
- **Words of the interface**: in French a run of the agent is now always « passe » (« passage » stays for a piece of
  text: a passage changed, the passage of a page), in the page, the settings and the notifications; « Report or
  suggest » everywhere « Report an error » was left; the links check reads a video (no longer « later »). Docs: the
  reference guide is watched every two weeks (its workflow runs every Monday and opens an issue every other week,
  sooner for an urgent advisory), not every week.
- **« What I already know » on a lead** (proposed by the user, who had to retype a lead with their own measurements
  as an idea to give them to the run): a note on any open lead of a check (`POST /api/verifications/{id}/note`),
  kept with the check and marked on the lead's line. It goes with its lead to the run inside an `<editor-note>`, said
  to be the editor's, unpublished, a check that is never cited nor written into the guide (`fix.EDITOR_NOTE`); the
  review shows it in the lead's block, the pull request only counts the leads that had one.
- **« Update my folder »** (proposed by the user, whose folder did not show a pull request merged until the next
  run): « To handle » says when the guide's folder lacks pull requests merged on the forge (which ones, the folder's
  branch, its changes not committed, when it last moved), and so does the page of a run merged when its pull request
  is not in the folder yet. The button moves the base branch forward as the agent already does before each run: a
  fast-forward only, what is not committed stays, the branch checked out is never changed (on another branch, the
  base alone moves), refused while the folder is lent to a run; when git refuses, nothing moves and the files in the
  way are named. The menu « Watch » counts it. At the retouch pause, the page says that what is saved there reaches
  the folder after the merge and this update, and names the pages retouched by hand outside the folder
  (`GET /api/folder`, `POST /api/folder/update`).
- **One menu « Watch », and a page « To handle » first** (proposed by the user, who found « Watches » and « Check the
  guide » alike): the watches, the checks, the sources followed and every run are entries of one menu of the bar,
  each with a line on where it starts from (every two weeks from the forge, or on demand). Its first entry, « To
  handle », is the first page: a run paused for the editor (or running), a watch to start, the checks whose leads are
  to sort, then « New check » and « Report or suggest »; it says that only a paused run is pressing, and the menu
  shows how many things wait. « Every run » lists the watches' runs with the others, newest first; the page of the
  watches keeps the watches only. On a check, a lead is sorted (« Sort », « to sort »), the run comes after. In a
  narrow window the menu's entries are lines of the folded header.
- **What is typed on « Report or suggest » is never lost** (proposed by the user): one draft per tab (an error, an
  idea, links), kept while switching tabs and in the browser against a reload, a crash or a closed tab (written half
  a second after the last key, and when the page is left), with « Clear » and « Restore ». It empties once the run or
  the check has started; a refusal or a lost connection keeps it and says why, where the button stayed greyed before.
- **Links to read whole** (D5 of the roadmap, proposed by the user): « Report or suggest », tab « Links to read
  whole », one address per line. Each link is read whole without a model (`links.py`: a page, a repository's README,
  a PDF with the optional `pip install "vault-watch-agent[pdf]"`; a video through dl-sub-dub), then one call per link with the whole guide,
  without the web (step `links`), lists what in it concerns the guide: leads « From a link », the link as their
  first source, ticked on the page of the check and sent to an addition run, which checks them on primary sources.
- **A video among the links** (D5): read through [dl-sub-dub](https://github.com/DamienBecherini/dl-sub-dub)'s
  route « text of a video » (contract 1, `videos.py`), on the editor's machine: its subtitles, or its audio
  transcribed; the model reads the site's description and chapters, then the words in paragraphs with their time.
  Set once in the settings (`videos`: its address, the reference of its token, the command that starts it); the tab
  says whether it is ready, and the agent never starts it.

- **The leads of what is new as a list that unfolds**: a title per lead, the source and the guide side by side,
  the passage of the guide opened in Obsidian at its heading, the sources cited as links, « Dig deeper » as a
  button, the sources and the pages to read also as lists, « How to read a lead » once above the list.
- **Dig deeper, on each line or for all the leads ticked**: a box « dig » on the line of each lead, « Dig every
  lead ticked » above the list, and in the bar « Dig nothing / Dig n of m / Dig all » with the price of the run part
  by part (plain leads, leads dug deeper, the cross-check and the mirrors); the button says how many are dug.
- **The bar of a check folded to one line**: what is ticked, its price, « Options », « Dismiss » and the button. The
  options open above it (kept open or folded in the browser): dig deeper and reading, then the steps of the run as
  cards (what each does, its engine, model and effort as chips, how it is paid; changed for this run: framed). On a
  phone, « ⋯ » opens them, a « ? » keeps what each step does, and a lead's title takes the whole width.
- A lead unticked is no longer dug deeper (it stayed dug, and counted, before): what may be ticked follows one rule,
  `static/rules.js`, tested with node (`tests/test_rules.py`, every order of the clicks).
- **The list of the checks says what each one is**: its kind in colour (guide health, lighter guide, what is new;
  `Check.kind`), a short title (« Links to read whole · 2 links », « 7 checks »), « from Report or suggest » when it
  was not started there, the links it read as links (a PDF named after its file when it has no title), and the
  history narrowed to one kind. A check on a subscription shows what it is worth at list price, struck through
  (so do a run's line, its progress, the lists of the runs and every estimate before a check or a run; the report
  says it in words),
  instead of 0.00 $. The runs its leads went to stay on its card while they wait for something, with the button of
  their step (Follow, Review, Approve publishing, Merge).
- **The review of a run, one block per lead**: its number and title on the check's page, its source, a link to the
  check, the English text the run was given folded once (it was under each correction); an addition shown as
  « Added after « … » » and the new text alone (the paragraph it follows was shown twice); a group of corrections
  ticked by one box that says why they go together and that a text is changed by retouching it; the leads left
  without a change in a frame of their own, at the top.
- **The retouches said plainly**: why lend the folder (Obsidian shows main and does not see the corrections until it
  is lent), what the editor here writes to (the run's copy, or the lent folder); each page changed with « Open here »
  and « Open in Obsidian » (once the folder is lent); the editor says what is not saved, and « Cancel my changes »
  goes back to the version last saved (Ctrl+Z still brings the changes back), « Close the page » when there is
  nothing to cancel.
- **Take my folder back** (`POST /api/runs/<run>/folder/back`): the folder lent to a run comes back to main without
  ending the retouches; what was changed in it is committed onto the run's branch, and the folder can be lent
  again. « Skip » drops those retouches too: the branch goes back to what the review applied.
- **The publish screen can correct and translate again**: « Before publishing » says one check a line (the guide's
  audits, the translation, the links to check yourself with their page and whether the run added them, the weight
  of the pages, each page a link down to it); each page changed is a line of one height (title, path, passages,
  « Correct », « Translate again » with its estimate), open: its source beside its translation, shown as additions.
  « Correct » opens the page and its mirror side by side at their first passage changed; « Save and check again »
  commits them as the editor's and the run checks again (`POST /api/runs/<run>/publish` `{action: "recheck"}`), or
  translates the French corrected first (`"retranslate"`), or a page from the start (`fresh`), then comes back to the
  same pause. The pull request names what was corrected there. The raw diff stays, folded.
- **The passages a run changed, in green in the editors** (the retouches, the publish screen), with « ◀ passage
  n / m ▶ » to go from one to the next; the editor opens at the first. A layer behind the text area holds the same
  text in the same box (width, borders, scroll bar), coloured through the CSS Custom Highlight API (`<mark>` where
  it is missing), and follows its size, the page's zoom, its scrolling and the typing; checked aligned to the line
  on the 16 texts of a real run at 80 to 150 % and at a phone's width.
- Every bar fixed at the bottom of a page leaves room for itself: the end of the review was hidden behind its bar.
- A long address no longer widens the columns of a text beside its translation past the screen.
- An addition run says what its leads came from (« links to read whole (add-…) », in its pull request too): it said
  « what a reader would look for and not find » whatever the check.
- **A lead in parts, in your language.** The page of a check draws a lead as its kind and pages, its text, then
  the pages to read also and its sources, short and clickable, instead of one block. A check started from the
  interface in another language than English has each lead explained in it (`detail`: what the source says, what the
  guide says, what remains to check, what it changes for the reader; `news.in_language`); the lead's line stays in
  English, since it is what a run, its report and its pull request read.

## 1.4.3 (2026-11-22)

- **Fixed: the page refused to open from a link of another site** (« a request from another site »): 1.4.2 refused
  any request the browser marks as coming from another site, the page itself included, so a link to it in Obsidian,
  a mail or a dashboard failed (typing the address, a bookmark or the terminal worked). Only the API refuses another
  site now; opening the page does nothing by itself, and its scripts call the API from the page.

## 1.4.2 (2026-11-22)

A security release: an audit of the whole agent found two serious flaws, present since earlier versions. Update.

- **Critical: another site could make the server send a secret away.** `GET /api/models` resolved a key reference
  given in its query (`env:`, `file:`, `sops:`) and sent it to the address of its query; a GET needed no header, so
  an `<img>` on any page the editor visited while `serve` ran (or a note rendered by Obsidian) was enough. Now every
  call of the API must carry `X-Vault-Watch` (the page sends it on every call), a request the browser marks as
  coming from another site (`Sec-Fetch-Site`, `Origin`) is refused, and only the browser's own requests go without
  it (the probes, a run's stream, its report). The page is never shown in a frame (`X-Frame-Options`, CSP
  `frame-ancestors`), runs only its own scripts (CSP) and is never sniffed. After updating, reload the page.
- **High: a correction could rewrite any file.** The page of a correction is written by a model from what it read;
  it was only required to exist. A correction on the guide's audit script, its manifest or a file outside the guide
  was applied once accepted, and the agent then ran that script. A correction now touches only a content page of
  the guide or its mirror (`vault.is_page`), else `not-a-page`; the editor's path stays in its tree.
- **The local network stays out of reach**: the address a page is actually read from is checked public, not only
  the one its name gave when checked (DNS rebinding); an IPv6 address carrying a private IPv4 (NAT64, 6to4, Teredo)
  counts as private; the notes of a watch item follow redirections one by one, each checked.
- **Links in http(s) only**: a source written by a model, or a feed item's link, that is not an http(s) address is
  shown as text, never as a link (`javascript:`); in the pull request, a source must be an address or a page.
- **Smaller**: a watch's `until` must be a date; sops gets `--` before its file and a field name of letters and
  digits; the manifest's `base_branch` must be a branch name; `Host: testserver` is accepted under the tests only.

Two bugs found by a new smoke test of the page (`tests/test_page_smoke.py`: every screen drawn in a headless Chrome,
in French and in English, wide and on a phone, without a JavaScript error, a refusal of the CSP, nor « undefined »):

- **Two watches of the same day get their own branch** (`chore/watch-<date>-<issue>`): an urgent watch and a regular
  one of the same date shared a branch and a worktree, the second run failing on the first one's corrections.
- **The page « Languages » failed** (« can't access property "onclick" ») when every page was in line with its
  translation.

## 1.4.1 (2026-11-21)

- **The page « Languages » says what it is for, and checks the edits before the sync** (H4 of the roadmap, asked
  by the user): you write in the guide's language, then ask for the other languages to follow. Before translating,
  three optional checks, each with its estimate, on the passages changed (`proofread.py`, `POST /api/mirrors/check`):
  spelling and grammar (the translation model, step `proofread`), truth and relevance on the web (the reasoning
  model, step `factcheck`), consistency with the rest of the guide (the cross-check, the whole guide read). Each
  finding is a fix to tick or leave, its text editable; the fixes ticked are written in the guide's folder as if
  typed (`POST /api/mirrors/check/<id>/accept`), then translated with the rest.
- **An item without text reads its own page** (C3 of the roadmap): a kept item whose feed gives no text (a blog
  post, a press release, a model page: 20 of the 115 kept by the watch of 19 November 2026) gets the start of its
  own page as notes, read at collection without a model (`Collector.page_notes`, the agent's page reader; public
  addresses only, `read_pages=False` to turn it off); a GitHub repository gives its README, a video page (YouTube,
  drawn by scripts) is not read. On the guide's collection of 21 November 2026: 37 of the 77 items kept, 17 seconds
  for the whole collection. The model reads the primary source instead of a title.
- A video keeps its whole description as notes (YouTube gives it in `media:description`; only its first 220
  characters were kept, as the summary). On the guide's channel, the descriptions are mostly promotion: the
  subtitles are where a video says something (D5 of the roadmap).
- The report of a watch says where the claims past their « Recheck by » date are re-checked: the check « claims »
  of « Check the guide ».

## 1.4.0 (2026-11-21)

Phase H, the editor's hand: the human writes the final text. A proposal can be retouched in its card, the pages of
the branch can be retouched before the pull request (in Obsidian or in the page), and the mirrors follow whatever
changed, by hand or not. Tested for real on the IA on-prem guide: a sync of the languages (PR #105), a run of
corrections retouched in its card and in the folder lent to Obsidian, with a draft set aside and put back untouched
(PR #107), « Skip » after a retouch in the lent folder (nothing kept), and the folder clean after each merge.

- **The page « Languages » shows what changed**: each page ahead of its mirror (or edited in the folder) lists
  its changed zones, two lines of context above and below, the change as a word-level diff (`mirrors.hunks`).
- **The translation beside its source**: the `mirror` step keeps, for each page, what changed in the source and what
  the translator made of it (`mirror_pairs`); the publish screen shows them side by side, as word-level diffs. A
  « Sync the languages » run stops after the translation for its review (`translation`, `POST
  /api/runs/<run>/translation`): the translation can be retouched there, the translator's text kept. The screens of a
  run that is not a watch no longer say « Watch up to » nor count corrections it does not have.
- **A pause to retouch the pages** (H3 of phase H): after the corrections are applied on the branch and before the
  mirrors, the run stops (`retouch`). « Lend my folder to this run » puts the guide's folder on the branch, detached
  at its tip, for Obsidian; what it held and was not committed is set aside in a stash named after the run and put
  back after (`retouch.py`); an editor in the page writes into the lent folder, or into the run's worktree. « I am
  done » commits the retouches as the editor's, moves the branch, gives the folder back, and the mirrors, the checks
  and the links follow; « Skip » drops what was typed. `resume --retouch done|skip` on the command line. A banner
  while the folder is lent or something set aside is not back. Runs started before resume without the pause.
- **A proposal retouched in the review** (H2 of phase H): « Retouch » on a card makes its text editable, the diff
  following; the free checks run again on it while typing (`POST /api/runs/<run>/retouch`, `graph.retouched`), and
  the review sends the texts with the ids (`{"accept": [...], "edits": {"C3": "..."}}`; `resume --edit C3=file`).
  The editor's text applies and its mirror follows; the model's is kept (`proposed_model`) and in the report; the
  pull request marks the correction ✍️ and counts the retouches.
- **Sync the languages** (H1 of phase H): the page « Languages » and `vault-watch mirror` list the source pages ahead
  of their mirror (from git: the text changed since the last commit of the mirror, not the dates) and those changed
  in the guide's folder and not committed; the pages ticked are translated, passage by passage, in a run that ends
  at the pull request like the others. The pages of the folder go onto the run's branch with their translation;
  once merged, the folder's copies are put back in line before it moves forward (`vault.settle`).
- The `mirror` step follows the diff of each source page on the branch (`mirrors.py`), paragraph by paragraph, a
  table row or a list line at a time, instead of the corrections one by one: it carries whatever changed, edits by
  hand included.

## 1.3.2 (2026-11-21)

Documentation only: nothing changes in what the agent does.

- The documentation is easier to find one's way in: an index, [docs/README.md](docs/README.md) (and in French), with
  every page grouped by the question it answers and a map; the French pages moved to `docs/fr/`, under the same
  names as the English ones, which stay where they were; the screenshots moved to `docs/images/`.
- Three new pages, in English and French: [A run, step by step](docs/run.md) (what each step of a watch reads and
  decides, what can stop an edit, the watch of 16 November 2026 with the cost of each step, the review and publish
  screens); [Check the guide](docs/check.md) (the eleven checks with their estimate and what they cost, the life of
  a lead, the runs the leads go to, « Report or suggest »); [Costs](docs/costs.md) (what makes the price of a call,
  the prompt cache, where the money goes by kind of run, how the estimates are made and why they miss, where the
  prices come from, the journal, what lowers the cost).
- [Choose a model](docs/choose-a-model.md) says what each setting changes (engine, model and effort of a role, a
  step set apart, one run only, prices, the settings of an OpenAI-compatible server, and the choices made per run).
  [Chapters](docs/chapters.md) has a diagram of where a page's chapter comes from. New screenshots, in both
  languages: the catalogue of « Check the guide », the « Costs » page, the Settings (« Models and effort »), the
  « Sources » page.
- The idea the project comes from, at the top of the README and of the overview, with a diagram: a guide written as an
  Obsidian vault, starlight-obsidian-engine that publishes it on the web, and the agent that keeps it true. The agent
  edits the Markdown only and stops at the pull request; it works on any Markdown guide, published or not.
- A page of its own on the chapters, [docs/chapters.md](docs/chapters.md) (and in French): the three steps that work
  by chapter and what the number and the size of the chapters change for each, where the chapters come from, the
  automatic rule, why 150 KB and 20 KB (set on the IA on-prem guide, fixed in the code), what a split that fits
  badly costs, and the chapters the IA on-prem guide declares.
- The roadmap has a phase H, « the editor's hand »: mirrors that follow the diff and a « Sync the languages » button,
  a proposal retouched in the review, a pause to retouch the pages of the branch (in Obsidian or in the page) before
  the mirrors.

## 1.3.1 (2026-11-20)

- Documentation read again against 1.3.0, in both languages: the pages of the interface and the commands in the
  README, the sizes, the modules and the tests of [docs/code.md](docs/code.md), what was produced and what it cost
  in [docs/presentation.md](docs/presentation.md), what leaves the machine in [docs/security.md](docs/security.md).
- The amounts of the reference guide's cost journal are said to be indicative (the API's list price): its author's
  calls went through the API access of his Claude subscription.
- New screenshots, taken on the reference guide: the review screen with the header of 1.3.0, the leads of what is
  new, the chapters.
- Interface, labels: « Create an addition run with n lead(s) » (it said « a addition run with n point(s) »); a
  lead sent to a run reads « → run », whatever the kind of run (it said « → fix run » for an addition or a
  compaction too); « dig deeper » says what it changes (several sources, more searches) now that every lead has a
  call of its own.

## 1.3.0 (2026-11-20)

Look for what is new: what a reader would look for in the guide and not find. A watch follows the sources it
already knows, and what it sets aside as a possible addition is never written. [docs/news.md](docs/news.md).

- The leads: the check « What is new: what a reader would look for and not find » of « Check the guide » (or
  `vault-watch news`, which says its cost and asks first). One call reads the whole guide, without the web, and
  lists at most 30 leads: what the guide presents as current and has probably moved on, the subjects a reader
  would expect and no page covers, and the items past watches set aside as possible additions (read from the
  reports of the runs kept on the machine, the last 120 days, no model). A lead is a question: nothing is verified
  and nothing is edited. The guide's own threshold for additions (its brief) is given to the model.
- The additions: the leads kept go to an addition run (`vault-watch fix <thread> --findings … --add`). Each lead is
  checked on primary sources on the web, then written where a reader would look for it, corrected where the guide
  states something superseded, or left with its reason; a subject that needs a page of its own is said, the page
  is not written. One lead per call (the web of a call has a ceiling of 20 searches and 30 pages, which leads in
  one call would take from one another). What two calls add to one page is put together by the program: a footnote
  marker both chose is renamed, and two edits that write after the same passage both apply, in the order proposed.
  Then the cross-check of a watch, which reads the whole guide, the review, the mirrors, the guide's audits and the
  pull request, on a branch `feat/<thread>`.
- A second way to find leads, from the web instead of the guide: the check « What is new: the web explored,
  chapter by chapter » (`vault-watch news --explore [--chapters …]`). One call per chapter chosen, each with the
  web and the whole guide, searches freely what moved on the chapter's subjects and keeps what no page says; its
  leads are facts with the sources that establish them, and go to the same addition run. It finds what nobody
  thought to ask, and pays for the web before the editor has seen anything; the cost follows the chapters ticked.
- A lead can be dug deeper (a box beside it; `!` at the start of its line on the command line): its call in the
  addition run is asked for a fuller look, on several independent sources and several pages if need be.
- What each lead's call reads is chosen when an addition run is created (a list on the leads page, `--context` on
  the command line): the whole guide, or (the default) the pages the lead names and the plan of the guide (every
  page with its path, weight, title and headings), 50 to 90 KB instead of 830 on the IA on-prem guide, cached for
  that call alone. A lead now says which pages to read: the call that lists the leads has the whole guide before
  it, and names after « Read also: » up to six pages one must have read to write the lead well. A lead that names
  no page reads the whole guide all the same (cached and shared on the Claude API, one call after the other
  elsewhere), and the cross-check reads every page either way. Measured on a run of five leads: 8.72 $, where the
  whole guide would have been about 17 $; the calls wrote 16 edits and the cross-check added 19 on pages they had
  not seen, every place that stated the older values was reached. The button shows the price of the choice.
- A lead its call could not look at (the web of the call ran out, the call failed) is marked « not checked by the
  run » on its verification, with the reason and a button that puts it back among the leads to handle.
- What an addition run does not write is said where the editor reads: the run never writes a new page, and the
  pages its leads would need are listed at the top of the review screen, of the report and of the pull request;
  the check cards carry the limit as a line of their own. The review also lists the leads left without an edit,
  and why.
- An idea or a piece of news of your own goes straight to an addition run, without a search for leads: the page
  « Report an error » becomes « Report or suggest », with a tab « An idea or a piece of news to dig into » (and a
  link from « Check the guide »).
- A step can run on its own engine, not only its own model and effort (`steps.<step>.engine` in the settings, an
  optional key of schema 1; « Set a step apart » has a column for it): the search for what is new through a
  subscription while the watches stay on the API, for instance. An engine that cannot be set up is said when its
  step is asked, not for the runs that never reach it. An agent older than 1.3.0 ignores the key.
- The engine, the model and the effort of a step can be changed for one run only, where the run is started,
  without opening the Settings: every check card and every button that creates a run shows what will run each
  step and how it is paid, with « change for this time ». The choice is kept with the run (`runs/<thread>.json`
  in the guide's working folder), so the steps that come after a pause follow it; the Settings are not touched.
  The estimates follow it. `GET /api/steps` says how each step would run.
- The home page no longer waits for the forge at every display: the state of a merged or closed pull request is
  kept on the disk, the open ones and the list of watch issues are asked again at most every 20 seconds and side by
  side, and the page draws what it showed last before it refreshes. Measured on the IA on-prem guide: 1.7 s for
  the first display after a start, 15 ms after.
- The chapters of a guide are no longer its top folders only ([`[[chapter]]`](docs/connect-your-guide.md#chapter)).
  The manifest can declare them (`[[chapter]]`: a name, paths, and `explore = false` for a chapter left unticked
  when the web is explored), an optional part of schema 1 that an older agent refuses as an unknown key. A model
  can propose them: page « Chapters » of the interface, or `vault-watch chapters --propose`; one call reads the
  outline of the guide (path, weight, title and headings of each page, not the text) and names the chapters, those
  not to explore by default, and why. The page also edits them by hand, shows what a split would give before it is
  saved, then writes the manifest on a branch with its pull request. For the pages no chapter takes, and for a
  guide that declares none, the automatic rule now splits a folder heavier than 150 KB (along its subfolders, else
  in slices of pages) and gathers the top folders lighter than 20 KB: on the IA on-prem guide, the lexicon (219 KB)
  becomes two chapters and the root pages join the project pages. The exploration, the check of the translations
  and the reading by chapter follow. `vault-watch chapters` lists them; `doctor` has a line for them.
- The header: the guide's name is a menu (its site, its repository, its chapters) instead of a row of links; the
  agent's code is in the footer. The link to the Claude API console is gone. Under 800 px of its own width (the
  size of the text counts), the header keeps the agent and the name of the guide and folds everything else under
  one button: the pages, the guide's links, the agent's code, the tools.
- « Give my opinion », a button of the header with its icon (and of the footer): a note out of five, a kind
  (opinion, bug, idea), a message, all optional. The agent sends nothing: the reader opens an issue of the agent's
  repository with the form filled in (`.github/ISSUE_TEMPLATE/feedback.yml`; public, a GitHub account), or copies
  the text, or sends a mail from their own mail program, without an account (`web.FEEDBACK_EMAIL`). What is sent
  is shown first: the version always, the system, Python, the engine and the kind of screen when a box is ticked,
  never anything of the guide. A fourth kind, « a security flaw », never opens a public issue: its button opens
  the private report of the repository (the message copied, to paste there), and the mail stays.
- The runs kept on the machine stay light (`store.py`): LangGraph writes the whole state of a run after each step,
  and only the last copy is ever read. The copies before it are removed when a run pauses or ends, when a command
  that runs one ends and when the server starts, and the space is given back to the disk. On the IA on-prem guide:
  26 runs, 45.6 MB before, 5.1 MB after, every run shown as before, and a paused run goes on from where it waits.
- Accessibility of the interface: the text is 16 px (it was 15), what goes with it 14 px at least (the footer was
  12, notes 13), short labels 13 px (there were some at 11 and 12); the keyboard always shows where it is; what is
  finished or rejected has a quieter frame instead of a faded text (a faded note fell under 3:1); small buttons and
  the box of a correction are easier to aim at. Measured on every screen, light and dark: every text at 4.5:1 or
  more against what is behind it.
- The leads of a check read as what they are. The passage shown under a finding is what the guide says today: it
  is labelled so and highlighted in yellow (it had the green of an added line, and read as a proposed addition);
  the leads of « What is new » say that nothing is written yet and that the run may correct what is out of date as
  well as add. « Check the guide » has « Tick all », « Untick all » and « Only the free ones » above its checks.
- The lists scale with the runs kept: the home page reads the state of a run only when it has moved (one line of
  the database per run otherwise), shows the 20 newest runs outside the watches and offers the older ones;
  « Check the guide » offers the verifications older than the 20 newest, which no screen listed before. A run
  just created is listed at once, before its proposals are made.
- Four steps more in the Settings (the leads, the exploration, the additions, the split into chapters), each of which can run on a model
  of its own. The button that creates an addition run shows an estimate that follows the leads ticked and dug.
  The estimates of the leads and of an addition run are set on real runs (2026-11-20, the IA on-prem guide:
  2.28 $ for 28 leads; with the whole guide, 11.01 $ for a lead about six price lists and a lead dug deeper, then
  12.94 $ for three leads; with their pages and the plan, 8.72 $ for five leads): with the whole guide ≈ 6.30 $
  plus ≈ 2.15 $ per lead (≈ 2.80 $ dug deeper), with the lead's pages ≈ 4.30 $ plus ≈ 1.10 $ per lead (≈ 1.50 $
  dug deeper). The cross-check costs about 4 $ whatever the leads. The exploration and the proposal of chapters
  by a model (0.13 $ once) are not set on more than that.
- The values a run removes are looked for in the text of the pages only, no longer in their front matter
  (`verified_by: "Fable 5.1"` was 33 of the 35 lines listed by the first addition run).
- `prompts.fill` knows two markers more: `<<TODAY>>` and `<<BRIEF>>` (the guide's contract, put last).
  `compact.in_calls` is the part of the compaction proposals that makes several calls, now shared.
- Fixed: on Windows a page of the interface could fail to read a check or the sources file at the instant the
  server was putting a new version in place (a test failed about once in twenty runs); the reads now wait for
  the swap, as the writes did.

## 1.2.0 (2026-11-20)

Compaction (M6): keep a guide from growing heavy. A watch only adds; the IA on-prem guide went from 572 KB to
891 KB in 90 days. [docs/compact.md](docs/compact.md).

- Sizes (`sizes.py`, no model): what each page weighs, what it gained in 90 days (read from Git), its heaviest
  sections and what its footnotes weigh. A page is flagged when it grew much against itself: 5 KB or a quarter of
  what it weighed (`[budget] growth_kb`, `growth_percent`), shown with its size now and what it gained. No ceiling
  by default, since how long a page should be depends on its subject; a guide can set one (`[budget] page_kb`,
  `[budget.pages]` for the pages of a folder). Four optional keys, an addition to schema 1. Shown by
  `vault-watch compact`, by a line of `doctor` and by the check « Size of the pages »; a flagged page is a
  warning, never a failure, and a read-only page is never flagged.
- The report: the check « Compaction: what makes the guide heavy » of « Check the guide » (or
  `vault-watch compact --report`, which says its cost and asks first). One call reads the whole guide, with its
  heaviest pages named, and lists what is repeated in several pages (and which page should keep it), what is
  piled-up history, and which sections are longer than what they say. It edits nothing.
- The trims: the findings kept go to a compaction run (`vault-watch fix <thread> --findings … --compact`), which
  proposes targeted edits and takes the path of any run: a cross-check written for trims (is anything lost, does
  the page still read on), the review, the mirrors, the guide's audits, the pull request, on a branch
  `compact/<thread>`. No web, no sweep. The pull request says what the changed pages weighed before and after.
  The proposals take several calls when the findings are many (those that share pages together): the trims of
  thirty findings would not fit in one answer. On the Claude API every call reads the whole guide: the first one
  writes it to the prompt cache, the others start once it has begun to answer and read it (`llm.Claude.parse`
  takes `started`, outside the engine protocol). With another engine, or a guide too large for the model, each
  call reads the pages its findings name. A call that fails leaves its findings without a trim, said in the
  report of the run, and the others go on.
- What the code checks itself: a passage removed whole leaves no hole (a table keeps its rows, a paragraph does not
  leave two blank lines; this holds for every run); the definition of a note that a trim leaves without a sentence
  citing it is removed with it; a trim that would leave a sentence citing a removed note cannot be applied; and
  each trim lists the versions, advisory ids, amounts and links that no page states any more once the trims apply.
- Two steps more in the Settings (the report, the trims), with their effort (`high`). The button that creates a
  compaction run shows an estimate that follows the findings ticked: the cross-check, then a share per finding,
  at the prices of the models of the Settings.
- The Sources page: a proposal can be put off until the next check (« Put off », `POST /api/sources/later`): it
  leaves the list to decide, nothing changes in the guide, and the next check proposes it again if it still holds.
  A text filter above the table (name, repository, type, state). The table fits the page (the note « nothing
  since » on two lines, a long address wraps in its column); when it is wider than its card, the card says so: a
  shade on the side that hides columns, the first column stays in place, and an arrow stays at the bottom of the
  window while the table is there.
- A pull request with many corrections is opened: its description goes to `gh` in a file (as an argument, Windows
  refused it over 32 767 characters, before `gh` ran) and stays under what GitHub accepts (it loses, as far as
  needed, the passages under its findings, the end of its « Why » cells, then the last rows of its table). The
  commit messages, which name every correction, go to `git` on its standard input for the same reason. A
  publication that fails says so on the publish screen, which showed nothing.
- Every run says what it changes in the weight of the pages it edits: expected in its report, before the review
  (« Weight, if every valid correction is applied », with the three pages that change the most), measured in its
  pull request and on the publish screen. A watch that adds 5 KB to one page shows it before the review.
- A step can be set apart from its role (« Models and effort », « Set a step apart »; `steps` in the settings, an
  optional key of schema 1): its own model, and its own effort taken as it is. Made for the compaction on the
  strongest model while the watches keep theirs. The calls of that step go to a client of their own (`llm.Routed`,
  the step read from the label of the call); the estimates, the journal and the way the guide is read (whole or by
  chapter) follow the model of the step. An agent older than 1.2.0 ignores the key, and drops it when it saves the
  settings.
- A request to the Claude API may now write what its model accepts (128 000 tokens on the current models, read from
  the Models API) instead of 32 000, thinking included. The whole-guide checks wrote 27 to 29 k on Opus 5.5 at
  effort high, and the first compaction report on Fable 5.2 at effort high was cut at 64 000, the limit tried
  first. An answer cut at the limit is billed and lost: it is now written to the cost journal (`cut`, its output
  counted at the limit), the error says what it cost, and a check that failed this way shows that cost. The
  compaction report lists at most 30 findings.

## 1.1.0 (2026-11-19)

The sources of the watch, questioned over time: what each one brings (1.0.1), whether it is still there and still
fits the guide, and pages watched for what no feed publishes.

- Watched pages: a feed of type `page` reads a page at each watch (a price list, a compatibility table) and tells
  when it no longer says what it said, with what is gone and what is new as the item's notes. `watch`, a regular
  expression, chooses what counts (the lines that hold a price, for instance). What the page said travels in the
  watch (`pages` in `watch.json`, an addition to schema 1); the next collection compares with the most recent
  watch (`vault-watch collect --previous`, or those of the working folder). The reusable workflow `collect.yml`
  fetches the previous watch from its last run (`actions: read` in the caller). Asked for after the Lambda prices
  of 16 November 2026, which no feed saw.
- « Check the sources » (`sourcecheck.py`, the Sources page): each source is asked what it says today (there or
  not, archived, renamed, its last publication), the guide is read again (the repositories and Hugging Face
  publishers it cites and no feed follows, the feeds no page names any more, the tools followed for their releases
  and not for their advisories), and the page lists proposals to remove, change or add. No model, nothing billed.
  The ticked ones go to one pull request on the feeds file, whose other lines are not touched. A source quiet for
  180 days is said, never proposed for removal. GitHub is asked with the token of `gh` when the environment has
  none. First check of the IA on-prem guide: 63 sources in 12 seconds, 58 fine, 5 quiet for more than 180 days
  (exo, Aider, Khoj, two Hugging Face publishers), 25 proposals.
- The Sources page follows the pull requests it opened: a merged one takes its proposals away and brings the list
  up to date, a closed one gives them back to decide; the title counts what is left. A group of proposals, or all
  of them, is ticked in one click. First pull request made from the page on the IA on-prem guide: 21 sources
  added, no other line of its feeds file touched; one of them (the advisories of Arize Phoenix) brought a critical
  advisory of 9 November 2026 that no source followed.
- Correction of the 1.0.1 notes below: Aider's feed is not broken. GitHub's releases.atom also lists tags, and
  Aider's last one is of 12 February 2026: the project is quiet, which the check now says.

## 1.0.1 (2026-11-19)

- « Sources » page (`sources.py`, `GET /api/sources`): for each feed of the guide's `feeds.json`, what it brought
  over the watches kept on the machine and what became of it in the runs (kept by the rules, judged and kept by
  the model, corrections proposed and accepted), with the verdict of a stated rule: in error, noise, silent,
  leads without follow-up, few items, useful. No model, no network. Security advisories are never called noise.
  A run's items now keep the feed they come from. First reading on the IA on-prem guide (6 watches, 25 September
  to 16 November 2026, 63 feeds): 7 feeds led to an accepted correction, all of them releases or advisories of a
  tool; 16 gave no item over those seven weeks.
  The table sorts by any column (a click on its title, a second one reverses) and filters by state (one or
  several).
- A check of the guide that a stopped server left unfinished could not be handled: dismissing its leads or sending
  them to a fix run answered « the check is still running », for ever. Its leads are now handled like those of a
  finished check; the page says it was interrupted and which checks it did not reach; a check can be deleted.
- Replace, do not pile up (C2): the steps that write a correction (proposals of a watch, fix runs) are told to state
  the current fact in place of the old one, the history staying in Git; an old value is kept only when the reader
  needs it to act. The cross-check already judged it. This changes the prompts of every guide.
- The review page warns when a run made so far without a bill (a subscription, a local model) would continue on a
  billed engine, because the settings changed or another server resumes it. Seen on 19 November 2026: a fix run
  started on Claude Code had its translation billed to the API (0.16 $), the settings naming the API.

## 1.0.0 (2026-11-19)

M5: stable. The manifest, `watch.json`, the engine protocol and the settings are frozen at version 1
([docs/compatibility.md](docs/compatibility.md)); a guide can live on Gitea; the docs are written for someone who
is not the author.

- What a newcomer reads (T5.3): the README (EN, FR) rewritten around « your guide, your model, your decision »,
  with a quick start, what each part needs, the three engines and the forges; the IA on-prem guide is now the
  reference example, with its measures. `docs/security.md` (EN, FR): keys as references, what the model can and
  cannot do, what it reads is data, the local server, what to know before connecting a guide. `docs/code.md`
  brought up to date (three engines and plug-ins, two forges, the two modules it missed).
- The agent's folder (settings, the runs of each guide) and the cost journal are no longer created in the current
  folder: `~/.vault-watch/` and `~/.vault-watch/usage.jsonl` by default, so that a command run from a guide's folder
  writes nothing into it. A `.vault-watch` folder and a `metrics/usage.jsonl` already in the current folder (how the
  agent ran before, from its own clone) are still used; `VAULT_WATCH_HOME` and `VAULT_WATCH_JOURNAL` still win.
- Freeze (T5.2): the manifest, `watch.json`, the engine protocol and the settings each carry a version number, all
  `1`; `docs/compatibility.md` says what may change within a number (additions only) and how a new number comes
  (refused when newer than the agent, migrated when older). The settings get `"schema": 1` and their migrations
  (`config.MIGRATIONS`; a file without the number is read as 1); `EngineKind.protocol` (an engine package of
  another protocol is reported, not loaded). The watch source `github-issue` is now `issues` (a Gitea forge has
  issues too); the old name is still read.
- Gitea forge: a guide on a Gitea server says so in its manifest (`[guide] forge = "gitea"`, `forge_url`, and
  `forge_token`, a reference to the token: `env:GITEA_TOKEN` by default, or `sops:file#NAME`, `file:path`). The
  agent then reads the watch issues, downloads the Actions artifacts (Gitea 1.23 or later), opens the pull request
  and follows its state through the Gitea API; the branch is pushed by git as before. `doctor` checks the
  repository with the token; the interface names the forge and links the repository on it. GitHub is unchanged.
- Manifest: `[content] readonly`, pages the agent reads but never edits (generated pages, dated statements): a
  correction on one is refused (`read-only`), whatever step proposes it (proposals, cross-check, sweep, fixes), and
  every prompt is told. `[watch] changes_page`, a page where a watch records changes as dated lines: every proposal
  step sees it whole, whatever the keywords found. `doctor` lists both. Found on the second real guide (T5.1).
- The workflows use the actions that run on Node 24 (`setup-python@v7`, `checkout@v7`).
- `vault-watch collect`: a moving tag published as a release (`stable`, `latest`, `next`, `v1`…) is dropped at
  pre-triage, the real release kept; `docs/collect.md` says that `exclude` matches « owner/repo title ». The IA
  on-prem guide's collection is unchanged (166 items, 104 kept, both versions).

## 0.6.1 (2026-11-18)

- Python 3.11 works again: 0.6.0 stopped at its start on 3.11 (a backslash in an f-string's expression in
  `webtools.py`, which only 3.12 accepts; the engines' registry loads that module). A test now finds the f-strings
  3.11 refuses, whatever Python runs the tests.

## 0.6.0 (2026-11-18), M4: any model

- Engines are a protocol (`llm.Engine`: `parse`, `capabilities`, optional `count_tokens`) and a registry
  (`llm.engines()`): the Claude API, Claude Code, the OpenAI-compatible server, and any engine another package
  declares (entry point group `vault_watch_agent.engines`, an `EngineKind`). The Settings list the engines installed.
  `USAGE_KEYS`: what every usage returned holds.
- Contract tests (`tests/engine_contract.py`): what any engine must do, against recorded answers (a valid answer and
  its usage in the journal, an answer out of the schema, a refusal, a cut answer, a call with the web). The three
  engines pass it.
- The OpenAI-compatible engine (`openai_compat.py`): any server of `/v1/chat/completions`, hosted or local (llama.cpp,
  vLLM, Ollama, LM Studio). Its address, a key by reference, a model per role (the server's list offered), its
  window, structured output by `response_format` with the JSON schema or, when the server refuses it, the schema in
  the instructions and a tolerant reading of the answer; billed per token through the price table, or local and not
  billed. The context opens the system message, so that a server that caches a prompt's prefix (OpenAI, vLLM,
  llama.cpp, DeepSeek… automatically) reads the guide from its cache; the tokens it served are counted apart
  (`cache_read`). Anthropic's OpenAI layer has no cache: the engine says so in its capabilities.
- Web tools for a model without web of its own (`webtools.py`): search through SearXNG and page reading, run by the
  agent within the API engine's limits (20 searches, 30 pages per call). Only public addresses are read (never the
  machine itself or the local network, checked again after each redirection), the readable text of a page is cut at
  30,000 characters, a PDF is not read. Without a SearXNG address the model reads pages but cannot search, and the
  steps that check on the web say so (`steps.lacks`: « search »).
  Those searches are counted in the journal (`web_searches`) but not priced: they cost nothing.
  The page's text leaves out the empty items, headings and cells that icon menus leave (GitHub pages had dozens).
- Settings: the engine « OpenAI-compatible server » and its options; the cost shown before an action says « local
  model, not billed » or « billed by your provider » instead of a Claude estimate. Model ids of any form can be priced.
- What a call keeps beside the guide follows the model's window: 100k tokens with a window of 300k or more, a third
  of a smaller one (8k at least). A fixed 100k left a model of 64k tokens a negative budget, and even a small guide
  was cross-checked chapter by chapter (seen on the first run on a local model).
- The OpenAI-compatible engine, in `structured = "auto"`, puts the schema in the instructions whenever the server
  refuses a request carrying one (servers word that refusal their own way; Anthropic's OpenAI layer only takes strict
  schemas).
- `docs/write-an-engine.md` (and in French): the protocol, the capabilities, declaring an engine, the contract tests;
  its example, an engine for Ollama's own API in 90 lines (`examples/engines/ollama_engine.py`), passes them.
- The list of Claude models no longer fails with an HTTP 500 when no API key is set (the SDK raises a TypeError
  there): the Settings say why and offer the models the agent knows. The « Guide » category names the `feeds` watch
  source (missing since 0.5.0).
- `vault-watch eval`: the judge is a Claude model whatever model ran the watch (`--judge api|claude-code`; by default
  the watch's engine when it is a Claude one, otherwise Claude Code with a subscription, otherwise the API), so that
  a local model does not score its own proposals. The result names the models of the run and the judge.
- `docs/choose-a-model.md` (and in French): the models the IA on-prem guide uses (Claude Opus 5.5 for reasoning,
  Sonnet 5.5 for the mirror), what each step asks of a model, what was tried beyond them (Qwen3.6-35B-A3B on an
  8 GB laptop GPU: no proposal on watch #77, where Opus made three), and `vault-watch eval` with its limits. No
  other model is promised.

## 0.5.0 (2026-11-18), M3: any watch

- The watch format is a contract: `docs/watch-format.md` (and in French) describes `watch.json` key by key, with a
  `schema` number. The loader checks it: a newer schema is refused with « update vault-watch-agent », an item
  without `title` or `triage`, a `triage` other than keep or drop, a watch without `until` or a file that is not
  JSON are refused with what is wrong and where. Every watch of the IA on-prem guide since October follows it; the
  sample guide's watch now dates its two dropped items and declares `schema = 1`.
- Watch sources (`watches.py`): the manifest's `[watch] source` gives the watches of the interface. `github-issue`:
  the issues with its label, as before. `file`: a `watch.json` of the guide or a folder of them, listed with their
  window and items kept, started from the page; a file that breaks the format is listed with what is wrong. `none`:
  no watch. The page shows an issue's number only for an issue.
- The forge (`forge.py`): the calls to `gh` (watch issues, their body, closing one, the workflow artifact, opening a
  pull request, its state, whether the repository can be read) are the methods of `GitHub`, behind a `Forge`
  interface a Gitea or GitLab forge can fill. The number of items is read from an issue title in French or
  English (« 73 éléments », « 73 items »).
- `vault-watch collect` (`collect.py`): the agent collects a watch itself from the guide's `feeds.json` (manifest
  `[watch] feeds`, with `floors` and `seen`), without a model. Feed types: GitHub releases, tags and security
  advisories, RSS and Atom, YouTube, Hugging Face authors and trending models, GitHub search. The rules drop
  pre-releases, routine patches (unless their notes mention a security fix), advisories of low severity or already
  fixed at the guide's floor, quantized variants and adapters, and items already seen; a High or Critical advisory
  the floor does not cover is urgent. A port of the IA on-prem guide's `watch-feeds.mjs`: on its 63 feeds and the
  same window, both give the same items, the same triage and the same notes (455 items, 241 kept, since 1 June).
  Only the standard library. `docs/collect.md` (and in French).
- `source = "feeds"`: the interface lists the watches collected in the guide's working folder and has a « Collect
  a watch » button (free); a second collection the same day never overwrites the first. `doctor` checks the feeds
  file. The sample guide has a `feeds.json` (real projects of the kind it describes) and a floors file.
- The reusable workflow `.github/workflows/collect.yml`: a guide calls it from a ten-line workflow; it collects every
  week, keeps `watch.json` as an artifact and opens the issue the `github-issue` source reads (label, artifact,
  window, urgent-only runs as inputs). `sample-watch.yml` runs it on the sample guide by hand.
- `docs/code.md` lists every module again, with its size.

## 0.4.1 (2026-11-18)

- A verification's file is written aside then put in place in one go: the page, which reads it every few seconds
  while the checks run, could read it empty in the middle of a write (seen as a test failing once on GitHub).

## 0.4.0 (2026-11-18), M2: prices and capabilities

- `prices.py`: a price is four rates (input, output, cache read, cache write) with its origin. Sources in order:
  the user's prices (`prices` in the Settings), a list fetched on request (`prices.json` of the home, with its
  date), the defaults shipped (`defaults/prices.json`, checked in November 2026; they were `llm.PRICES`). A dated
  model id takes the price of its model; a damaged fetched list is ignored, never read as a price.
- The journal records with each API call the price it was counted at and its origin (`price`, `price_origin`);
  `costs.py` adds up `cost_usd` as written and never recomputes a past cost. Since 0.2.0 (17 November 2026) the
  cache reads of Sonnet 5.5 count at 0.10 $ per million tokens (0.20 before); the lines written before stay as
  they are.
- Settings: `prices` (model id -> its four rates), checked when saved; a page that saves without them keeps them.
- `vault-watch prices show` lists the price of each model and its origin; `vault-watch prices update` reads
  LiteLLM's public list (the Claude models of Anthropic, USD per token turned into USD per million), shows what
  changes, and replaces the fetched list only on `--yes` or a yes typed at the prompt. A list that cannot be read,
  or holds no Claude model, changes nothing. Nothing is fetched without this command.
- Settings, a « Prices » category: each model's four rates and where they come from (set here, the list of a
  date, the default of 2026-11, no price), the models in use first; a price set here (checked: four numbers, 0 or
  more) and « back to the default price ». « Read the list » fetches LiteLLM's list and shows what it would change;
  « Replace with this list » puts it in place. Nothing is fetched without that click.
- Each engine declares what it can do (`llm.Capabilities`): the model's input window, structured output, web
  (and whether the model reads the page itself or a summary of it), effort levels, caching, billing, exact token
  count. The window comes from the Models API when it was read, else 1M for a model the agent knows and 200k for
  one it does not. The list of the models in the Settings no longer leaves out the models with a smaller window.
- The context decides how the guide is read (`reading.py`): the guide is counted once per run (exactly on the
  API, which counts tokens for free; else estimated from its size with a 15 % margin) and compared with the model's
  window minus a reserve of 100 k tokens, capped by `[budget] max_context_tokens`. Fits: the whole guide in one
  call, as before. Does not: the cross-check, its sweep and the coherence check run chapter by chapter (one top
  folder per call, with the pages the corrections change; a correction keeps the verdict of its own chapter), and
  the report, the review screen and the verification say « by chapter: a contradiction between two chapters can be
  missed ».
- The example manifest of the IA on-prem guide no longer sets `[budget] max_context_tokens` (it was 450 000, below
  the estimate of the guide with its margin, about 500 000 tokens: the cross-check would have gone by chapter).
- One table of the steps that call the model (`steps.py`): for each, the role whose model runs it, the effort it
  asks for and what it needs (the web, the whole guide). The call sites read their effort from it, and the Settings
  list each step of a role from it (`STEP_EFFORTS` of `web.py` is derived from it).
- The estimates of the checks say where their price comes from when it is the default or none; the Costs page
  counts the API calls by the origin of their price (the lines before 0.4.0: « list prices of the time »).

## 0.3.2 (2026-11-18)

- READMEs: the review screen right after the introduction (a new capture, English and French, from the replay of
  watch #77), a « What this repository shows » section, and the pull requests of the guide as a count (twelve)
  instead of the first three.
- Interface: the colon follows the language (" : " in French, ": " in English) in the review
  cards, the addition leads and the applied corrections.

## 0.3.1 (2026-11-18)

- The runs made before 0.3.0 stay visible once the IA on-prem guide has its manifest: they belong to that guide
  whether it is read with its manifest or without one (0.3.0 gave a guide with a manifest a new, empty working
  folder).

## 0.3.0 (2026-11-18), M1: any guide

- `guide.py`: the manifest of a guide (`vault-watch.toml`): name, repository, site, base branch, language, pages
  (include and exclude globs), mirrors, modified field, watch, rules, checks, budget. An unknown key or a wrong value
  is an error that names the key. Two manifests in `examples/`: the sample guide's, and the IA on-prem guide's,
  which finds the same 129 pages as the agent does today.
- The pages, the mirrors and the date an edit bumps come from the manifest (`vault.guide_of`): a guide without
  mirror has all its pages read, one without `modified_field` keeps its dates. A guide without a manifest is read as
  the IA on-prem guide (French, `en/`, `last_modified`), as before.
- The prompts describe the guide from its manifest (name, language, `[guide] description`, mirrors) and read its
  rules from `[rules]`; the mirror step keeps every declared mirror in step, in its language (it assumed French to
  English under `en/`). A guide without a mirror no longer reports « no English mirror ».
- The guide's own checks are the commands of `[checks]` (audits, claims due, source audit, version floors), run in
  a copy of the guide, `{out}` replaced by the JSON file the agent reads. A check the guide does not declare is
  « not checked » in the verification and on the publish screen, not a failure.
- The repository, the site, the base branch, the label of the watch issues and the name of the watch artifact come
  from the manifest. A guide without repository is local: no issue listed, no link to GitHub in the header.
- Every prompt names the guide and its language from the manifest (`prompts.fill`): cross-check, fix, verification,
  evaluation judge. The translation check and the translation fixes work on each declared mirror, in its language;
  a guide without mirror skips the translation check. A test fails if a string of the IA on-prem guide comes back
  into the code (outside `guide.legacy`, and `cli.py` until `--guide`).
- Settings: a « Guide » category, read-only, from the manifest: name, subject, language and pages, repository, site,
  branch, and each part (mirror, modified date, watch, rules, checks, context budget) provided or missing, with what
  a missing one switches off. Without a manifest it says the guide is read as the IA on-prem guide.
- A check the guide does not declare reads « not checked » on the publish screen and in the pull request (audits
  and source audit), instead of « passed » or « all answer ».
- `vault-watch init` writes the manifest of a guide from what its folder shows: the GitHub repository of its
  remote, its branch, the language of its pages, the folders that mirror them, the date field of their front
  matter, the tooling and the `_` folders (private notes, templates) left out, its npm scripts as hints for
  `[checks]`; each guess is commented, and what it writes is loaded before it is written. `vault-watch doctor` lists
  what is ready and what is missing before a run: the manifest, the pages, each mirror, git (the guide must be the
  root of its repository), `gh` and the repository, the watch, each check and its program, the engine (Claude Code
  signed in with a subscription, or the API key found). Exit code 1 when something stops a run.
- A guide without repository: « publish » keeps the branch on the machine (no push, no pull request, no issue to
  close); the button says so. Found by running the sample guide end to end on Claude Code.
- Docs: « Connect your guide » (`docs/connect-your-guide.md`, in French `docs/connect-your-guide.fr.md`): the
  manifest key by key, the formats the checks and the watch must produce, what each optional part unlocks, the
  sample guide as the worked example. The overview (`docs/presentation*.md`) is up to date: twelve pull requests of
  the guide, the cost journal of 17 November, the Claude Code engine, phase G.
- Default rules shipped with the agent (`src/vault_watch_agent/defaults/`): a watch brief (sources by tier, what a
  correction and an addition are, severity) and a translation policy, written from the IA on-prem ones without what
  is specific to that guide. A guide without `[rules]` gets them.
- `--guide FOLDER` on every command. Without it: `VAULT_PATH`, then the current folder when it has a
  `vault-watch.toml`, then `../ia-on-prem-vault` as before. Each guide has its working folder (checkpoints,
  worktrees, verifications) under `.vault-watch/guides/<repository>/`; the runs made before stay in `.vault-watch/`
  for the guide they belong to (recorded in `.vault-watch/guide.json`, nothing moved); the settings are shared. The
  page shows the name of its guide in the header and the tab title. A wrong manifest stops the command with the key
  to fix.

## 0.2.1 (2026-11-17)

- The search for a replacement of a dead link gets what each page says with that source (the lines that cite it
  and, for a footnote, the lines that call it): it had only the URL, and said it could not open the pages.
- The review takes the ids as a list or as one string "C1,C3": a string was read letter by letter, and the run ended
  with nothing applied.
- One git operation at a time on the guide's repository: a fix pass and a translation pass started together
  failed on git's `index.lock` (both updated the reading copy of main at once).

## 0.2.0 (2026-11-17), M0: ground

- One version, read from `vault_watch_agent.__version__` by `pyproject.toml`, `/api/health`, `/api/info` and the page
  footer (an install left in `site-packages` no longer shows its own version when the source runs).
- A verification and the proposals for reported errors read the guide as merged: `main` brought up to date with
  origin, in a copy of the agent (`.vault-watch/worktrees/read-main`), whatever branch or work in progress the folder
  of the guide holds. They read that folder before: on 17/11, still on an old branch, it lacked the corrections just
  merged (#78). The page of a verification shows the commit it read, and which check is running.
- Header: a link « Claude API » to the billing page of the Claude Platform.
- CI: the tests on Linux and Windows, Python 3.11 and 3.12 (`.github/workflows/tests.yml`).
- Sample guide (`examples/sample-guide/`): twelve pages about a made-up notes server, planted errors, a watch of eight
  items; a run with a fake model goes through it (`tests/test_sample_guide.py`).

### Baseline

What every later milestone is compared with (2026-11-17).

| What | Value |
| :-- | :-- |
| Tests | 75 passing (Windows, Python 3.12) |
| First full run after the two engines (watch #77, API engine) | 11 corrections, all applied; $3.44; merged as #78 |

Published `eval` scores (`metrics/eval/`, model engine: API):

| Watch | Variant | Guide commit | Proposals | Recall | Recall (corrections) | Precision | Lenient precision | Run cost | Judge cost |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: |
| #30 | full | 7cb34a3 | 4 | 0.154 | n/a | 1.0 | 1.0 | $3.42 | $0.08 |
| #30 | full, v2 | 7cb34a3 | 2 | 0.115 | 0.200 | 1.0 | 1.0 | $3.30 | $0.08 |
| #30 | full, v3 | 7cb34a3 | 3 | 0.077 | 0.133 | 0.667 | 1.0 | $1.48 | $0.08 |
| #30 | keyword | 7cb34a3 | 1 | 0.038 | 0.067 | 1.0 | 1.0 | $0.66 | $0.07 |
| #47 | full | 4ca9e00 | 0 | n/a | n/a | n/a | n/a | $0.42 | $0.00 |
| #47 | keyword | 4ca9e00 | 0 | n/a | n/a | n/a | n/a | $0.42 | $0.00 |

Watch #30 has 26 changes in its reference (15 of them corrections); watch #47 has none, so only its cost counts.

## 0.1.0 (2026-11-17)

The state before the modular work: an agent for one guide, the IA on-prem vault.

- LangGraph graph: triage of the watch, proposals in parallel, cross-check, deterministic checks, dead links, two human
  pauses (review of the proposals, review of the pull request), translation of the English mirror, pull request.
- Local web page (FastAPI, `127.0.0.1:4430`): the watches, the review, a check of the whole guide, a report of an
  error, the costs.
- Two model engines: `claude-code` (`claude -p` on the Claude subscription of the machine, nothing billed) and `api`
  (Anthropic API). Without a choice, Claude Code when it is signed in with a subscription; never a silent fall back to
  the API.
- Settings window: engine, API key given by reference only (`env:`, `file:`, `sops:`), models read from the Models API
  (1M context only), effort per role.
- Header tools ported from dl-sub-dub: size of the text, light and dark, palettes with a contrast check, browser
  notifications, French and English.
- Costs per call in `.vault-watch/usage.jsonl` (cache reads and writes included), the engine and effort of each call,
  and what the subscription spared.
