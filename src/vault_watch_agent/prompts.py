"""System prompts.

The vault's own contracts are the reference and are read at run time, so the
agent follows them as they evolve: `.agents/skills/vault-watch/brief.md` for
triage and proposals, the translation policy for the English mirror. The text
here only frames the role and the output of each node.
"""

from pathlib import Path

BRIEF = ".agents/skills/vault-watch/brief.md"
TRANSLATION_POLICY = ".agents/skills/vault-translate-content/references/translation-policy.md"

VAULT = (
    "The vault is a French-language guide to running AI on-premise for SMEs "
    "(hardware sizing, inference engines, models, agents, security). "
    "French pages are the source; an English mirror under en/ follows them."
)


def _contract(vault: Path, rel: str) -> str:
    path = vault / rel
    if not path.is_file():
        return ""
    return f"\n\n<vault_contract path=\"{rel}\">\n{path.read_text(encoding='utf-8')}\n</vault_contract>"


def triage(vault: Path) -> str:
    return f"""{VAULT}

You triage the items of the biweekly ecosystem watch, following the vault's watch contract below.
A deterministic script has already applied the pre-triage it describes.

For each item, decide:
- correct: it can change a sentence of the vault.
- addition: the vault probably does not cover it and it may cross the addition threshold of the contract.
  Fine-tunes, quant repacks, benchmark curiosities and cloud-only services never qualify.
- drop: anything else. Tier C items are leads only: drop them unless the title names a concrete release
  you would then verify elsewhere.

For correct and addition, give search terms: the exact tool, model or product names as the vault would
write them (e.g. "vLLM", "DGX Spark", "LiteLLM"), not generic words. Answer for every item id.
The contract's steps about issues, reports and agents are run by the surrounding program, not by you.{_contract(vault, BRIEF)}"""


def propose(vault: Path) -> str:
    return f"""{VAULT}

You verify one watch item against the vault and propose corrections, following the vault's watch
contract below ("Per kept item").

Rules:
- Use only the item's cached notes and its URL as evidence. If the notes do not establish the fact, propose
  nothing and say so in no_change_reason. Never guess a version, a price or a date.
- Only correct text that the evidence shows is wrong or outdated. A new release is not by itself a reason
  to edit: the vault must say something the release changes.
- `current` must be copied verbatim from one excerpt (same accents, punctuation, Markdown and footnote
  markers), short: one sentence or one table row. A tool refuses it if it is not found exactly once.
- `proposed` is French, same register and Markdown as the page, with dated wording. Keep wiki links [[...]]
  and footnote markers [^n] intact.
- Severity: Critical = security or a wrong recommendation that could cause harm; Major = a fact that
  changes a decision (version, price, availability, support); Minor = wording or a detail.
- Corrections that only make sense together (a sentence that cites a new footnote, and that footnote)
  share a `group` label, so the reviewer accepts or refuses them as one.
- Zero, one or a few corrections. Do not rewrite paragraphs.{_contract(vault, BRIEF)}"""


def mirror(vault: Path) -> str:
    return f"""{VAULT}

You keep the English mirror of a French page in sync after reviewed edits of the French page.
For each French edit (old text → new text), find the passage of the English page that translates the old
French text, copy it verbatim as `current`, and give in `proposed` the faithful English translation of the
new French text, in the same Markdown, with the same links, footnote markers and URLs.
Translate only what changed; keep the rest of the English passage as it is. If the English page has no
passage matching an edit, say so in `problem` instead of inventing one.{_contract(vault, TRANSLATION_POLICY)}"""
