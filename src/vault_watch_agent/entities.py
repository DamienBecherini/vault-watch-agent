"""Candidates grouped by entity and scored (ROADMAP D2), no model.

A model is announced under many names: « Qwen3-235B-A22B-Instruct-2507 », « Qwen3 30B-A3B », « qwen3 GGUF ». Its
family is its name without what tells one release of it from another (a size, the active parameters, a variant, a
quantisation, a date of release): « qwen3 » for the three. The registry shows together the candidates of one family,
so the editor can merge them (Registry.merge), and scores them together:

    score = the tier of each independent publisher (A 3, B 2, C or unclassified 1), added up, × the weeks it was seen

A publisher is the site, or the account on a site where anyone publishes (a GitHub owner, a Hugging Face
organisation, a subreddit); two pages of one site are one source. « Two independent tier B sources », the threshold
the guide's editors used by hand, becomes a computation: `corroborated`, two publishers of tier A or B at least.

The tiers are the guide's ([watch] source_tiers: its file of tiers, the same one its source audit reads; a list of
domains under « ## Tier A », « ## Tier B », « ## Tier C », or JSON {"A": [...], ...}). Without one, every source
counts 1 and nothing is corroborated by its tier.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

WEIGHT = {"A": 3, "B": 2, "C": 1, "": 1}
# A token that tells a release of a family from another: a size (7b, 1.5b, 8x7b), the active parameters (a22b),
# experts (16e), a variant, a quantisation, a date of release as YYMM (2507) or YYYYMMDD. Not any four digits: the
# number of a card (RTX 5090, RTX PRO 6000) is its name.
_VARIANT = re.compile(r"""(?:
    \d+(?:\.\d+)?[bmkt] | \d+x\d+(?:\.\d+)?b | a\d+(?:\.\d+)?b | \d+e | e\d+b
  | instruct | chat | base | it | thinking | reasoning | preview | exp | experimental | hf | latest | distill
  | gguf | awq | gptq | mlx | exl2 | onnx | fp4 | fp8 | fp16 | bf16 | nvfp4 | mxfp4 | int4 | int8 | w4a16 | w8a8
  | q\d\w* | iq\d\w* | \d+bit
  | 2[3-9](?:0[1-9]|1[0-2]) | 20\d{6}
)""", re.X)
# Sites where anyone publishes: the account is the publisher, not the site
_ACCOUNTS = {"github.com": 1, "huggingface.co": 1, "hf.co": 1, "gitlab.com": 1, "x.com": 1, "twitter.com": 1,
             "medium.com": 1, "youtube.com": 1, "linkedin.com": 2, "reddit.com": 2, "old.reddit.com": 2}
_SECOND_LEVEL = {"co", "com", "gouv", "gov", "ac", "org", "net", "edu"}  # co.uk, gouv.fr…


def family(name: str) -> str:
    """The family of a name, normalised as candidates.key: « Qwen3-235B-A22B-Instruct-2507 » is « qwen3 », « Mistral
    Small 3.2 24B » is « mistral-small-3-2 », « NVIDIA RTX PRO 6000 » stays « nvidia-rtx-pro-6000 »."""
    tokens = [t.strip(".") for t in re.split(r"[^a-z0-9.]+", name.lower())]
    kept = [t for t in tokens if t and not _VARIANT.fullmatch(t)]
    return re.sub(r"[^a-z0-9]+", "-", " ".join(kept or tokens)).strip("-")


def publisher(url: str) -> str:
    """Who published `url`: the site without its subdomains (docs.vllm.ai and blog.vllm.ai are vllm.ai), or the
    account on a site where anyone publishes (github.com/qwenlm, reddit.com/r/localllama)."""
    parts = urlsplit((url or "").strip())
    host = parts.netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    if not host:
        return ""
    if host in _ACCOUNTS:
        path = [p for p in parts.path.lower().split("/") if p][:_ACCOUNTS[host]]
        return "/".join([host.removeprefix("old."), *path])
    labels = host.split(".")
    keep = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-keep:])


def load_tiers(path: Path | None) -> dict[str, str]:
    """{domain: tier} from a file of tiers (Markdown: « - domain » lines under « ## Tier A/B/C »; or JSON
    {"A": [domains]}); empty when there is none or it cannot be read."""
    if not path or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError:
            return {}
        for tier in ("A", "B", "C"):
            listed = data.get(tier) if isinstance(data, dict) else None
            out.update({d.lower().removeprefix("www."): tier for d in listed if isinstance(d, str)}
                       if isinstance(listed, list) else {})
        return out
    tier = ""
    for line in text.splitlines():
        head = re.match(r"#{1,6}\s+tier\s+([abc])\b", line.strip(), re.I)
        if head:
            tier = head.group(1).upper()
        elif line.startswith("#"):
            tier = ""
        elif tier and (m := re.match(r"\s*[-*]\s+`?([a-z0-9.-]+\.[a-z]{2,})`?", line, re.I)):
            out[m.group(1).lower().removeprefix("www.")] = tier
    return out


def tier_of(url: str, tiers: dict[str, str]) -> str:
    """The tier of an address: its host's, or the one of the nearest parent domain listed; "" when none is."""
    host = urlsplit((url or "").strip()).netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    labels = host.split(".")
    for i in range(len(labels) - 1):
        if (found := tiers.get(".".join(labels[i:]))):
            return found
    return ""


def _week(day: str) -> tuple[int, int] | None:
    try:
        iso = date.fromisoformat(day[:10]).isocalendar()
    except ValueError:
        return None
    return iso[0], iso[1]


def weeks(candidates: list[dict]) -> int:
    """The weeks (ISO) one of `candidates` was seen in: the days of their sources, their first and last days."""
    days = [s.get("seen", "") for c in candidates for s in c.get("sources", [])]
    days += [c.get(k, "") for c in candidates for k in ("first_seen", "last_seen")]
    return len({w for d in days if d and (w := _week(d))})


def score(candidates: list[dict], tiers: dict[str, str]) -> dict:
    """The score of an entity (its candidates together): {score, weeks, publishers: [{publisher, tier}],
    corroborated}. The best tier counts for a publisher seen at several addresses."""
    best: dict[str, str] = {}
    for c in candidates:
        for s in c.get("sources", []):
            who = publisher(s.get("url", ""))
            if not who:
                continue
            tier = tier_of(s.get("url", ""), tiers)
            if who not in best or WEIGHT[tier] > WEIGHT[best[who]]:
                best[who] = tier
    n = max(weeks(candidates), 1)
    return {"score": sum(WEIGHT[t] for t in best.values()) * n, "weeks": n,
            "publishers": [{"publisher": p, "tier": t} for p, t in sorted(best.items(), key=lambda x: (-WEIGHT[x[1]], x[0]))],
            "corroborated": sum(1 for t in best.values() if t in ("A", "B")) >= 2}


def view(candidates: list[dict], tiers: dict[str, str]) -> dict[str, dict]:
    """{candidate id: {family, group (the ids of the other candidates of its family), score…}}: what the page shows.
    The score is the family's, every candidate of it pooled: two names of one model are one entity."""
    by: dict[str, list[dict]] = {}
    for c in candidates:
        by.setdefault(family(c.get("name", "")), []).append(c)
    out = {}
    for fam, members in by.items():
        scored = score(members, tiers)
        for c in members:
            out[c["id"]] = {"family": fam, "group": [m["id"] for m in members if m is not c], **scored}
    return out
