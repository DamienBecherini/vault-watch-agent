"""System prompts.

The guide is described from its manifest (guide.py): its name, language, subject and mirrors. Its own rules are the
reference and are read at run time, so the agent follows them as they evolve: the brief (`[rules] brief`) for triage
and proposals, the translation policy (`[rules] translation_policy`) for the mirrors. The text here only frames the
role and the output of each node.
"""

from pathlib import Path

from .guide import Guide, language_name
from .vault import guide_of

DEFAULTS = Path(__file__).resolve().parent / "defaults"  # the rules of a guide that gives none ([rules] in its manifest)
DEFAULT_BRIEF = DEFAULTS / "brief.md"
DEFAULT_TRANSLATION_POLICY = DEFAULTS / "translation-policy.md"


def describe(g: Guide) -> str:
    """The guide in two sentences: what and in which language, and its mirrors."""
    lang = language_name(g.language)
    about = f" It is about {g.description}." if g.description else ""
    mirrors = "".join(f" A mirror in {language_name(code)} under {folder} follows them."
                      for code, folder in sorted(g.mirrors.items()))
    return f"The guide « {g.name} » is written in {lang}.{about} Its {lang} pages are the source.{mirrors}{editing(g)}"


def editing(g: Guide) -> str:
    """What the manifest says about editing: the pages never edited, the page where a watch adds dated lines."""
    out = ""
    if g.readonly:
        out += (f" Pages matching {', '.join(g.readonly)} are read-only: read them, never propose an edit to them "
                "(a tool refuses it); when one of them would need a change, say so in your reasons.")
    if g.watch.changes_page:
        out += (f" A change the watch records goes to {g.watch.changes_page}, shown with the excerpts: to add a dated "
                "line, quote the page's last line (or its placeholder sentence) as `current` and give it followed by "
                "the new line as `proposed`.")
    return out


def fill(text: str, vault: Path, mirror: str | None = None) -> str:
    """A prompt written with markers, for the guide at `vault`: <<GUIDE>> (the guide in a few words), <<LANG>> (the
    language of its pages), and for a translation <<MIRROR>> (the mirror's language) and <<MIRROR_DIR>> (its folder)."""
    g = guide_of(vault)
    lang = language_name(g.language)
    about = f", about {g.description}" if g.description else ""
    text = text.replace("<<GUIDE>>", f"a guide written in {lang}, « {g.name} »{about}").replace("<<LANG>>", lang)
    if mirror:
        text = text.replace("<<MIRROR>>", language_name(mirror)).replace("<<MIRROR_DIR>>", g.mirrors[mirror])
    assert "<<" not in text, text[text.index("<<"):][:40]
    rules = editing(g).strip()
    return f"{text}\n\n{rules}" if rules else text


def _contract(g: Guide, path: Path | None, default: Path) -> str:
    """The guide's own rule file, or the agent's default when the guide gives none."""
    if path is None or not path.is_file():
        path = default
    rel = path.relative_to(g.root).as_posix() if path.is_relative_to(g.root) else f"vault-watch default: {path.name}"
    return f"\n\n<vault_contract path=\"{rel}\">\n{path.read_text(encoding='utf-8')}\n</vault_contract>"


def triage(vault: Path) -> str:
    g = guide_of(vault)
    return f"""{describe(g)}

You triage the items of the ecosystem watch, following the guide's watch contract below.
A deterministic script has already applied the pre-triage it describes.

For each item, decide:
- correct: it can change a sentence of the vault.
- addition: the vault probably does not cover it and it may cross the addition threshold of the contract.
  Fine-tunes, quant repacks, benchmark curiosities and cloud-only services never qualify.
- drop: anything else. Tier C items are leads only: drop them unless the title names a concrete release
  you would then verify elsewhere.

For correct and addition, give search terms: the exact tool, model or product names as the vault would
write them (e.g. "vLLM", "DGX Spark", "LiteLLM"), not generic words. Answer for every item id.
The contract's steps about issues, reports and agents are run by the surrounding program, not by you.{_contract(g, g.brief, DEFAULT_BRIEF)}"""


def propose(vault: Path) -> str:
    g = guide_of(vault)
    return f"""{describe(g)}

You verify a group of watch items against the vault and propose corrections, following the vault's watch
contract below (what to do with each kept item). The items are grouped because they touch the same pages (often several
advisories or releases of one tool): decide for the group as a whole.

Rules:
- Give one outcome per item. Several items about the same passage lead to a single correction that
  cites all of them in `item_ids`, never to competing edits of the same text.
- Use only the items' cached notes and URLs as evidence. If the notes do not establish the fact, propose
  nothing and say so in no_change_reason. Never guess a version, a price or a date.
- Only correct text that the evidence shows is wrong or outdated. A new release is not by itself a reason
  to edit: the vault must say something the release changes.
- `current` must be copied verbatim from one excerpt (same accents, punctuation, Markdown and footnote
  markers), short: one sentence or one table row. A tool refuses it if it is not found exactly once.
- `proposed` is in {language_name(g.language)}, same register and Markdown as the page, with dated wording. Keep wiki links [[...]]
  and footnote markers [^n] intact.
- Severity: Critical = security or a wrong recommendation that could cause harm; Major = a fact that
  changes a decision (version, price, availability, support); Minor = wording or a detail.
- Corrections that only make sense together (a sentence that cites a new footnote, and that footnote)
  share a `group` label, so the reviewer accepts or refuses them as one.
- Zero, one or a few corrections. Do not rewrite paragraphs.{_contract(g, g.brief, DEFAULT_BRIEF)}"""


def mirror(vault: Path, language: str) -> str:
    """Keeping the mirror in `language` (a code of the manifest's mirrors) in step with edits of the source."""
    g = guide_of(vault)
    source, target = language_name(g.language), language_name(language)
    return f"""{describe(g)}

You keep the {target} mirror of a {source} page in sync after reviewed edits of the {source} page.
For each {source} edit (old text → new text), find the passage of the {target} page that translates the old
{source} text, copy it verbatim as `current`, and give in `proposed` the faithful {target} translation of the
new {source} text, in the same Markdown, with the same links, footnote markers and URLs.
Translate only what changed; keep the rest of the {target} passage as it is. If the {target} page has no
passage matching an edit, say so in `problem` instead of inventing one.{_contract(g, g.translation_policy, DEFAULT_TRANSLATION_POLICY)}"""
