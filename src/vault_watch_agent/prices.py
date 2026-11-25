"""What a model call costs, and where each price comes from.

A price is four rates in USD per million tokens (input, output, cache read, cache write) with its origin. Three
sources, the first that knows the model wins:

    set       the user's own, in the Settings (`prices` of settings.json)
    fetched   the list fetched on the user's request (`prices.json` of the agent's home, with its date)
    default   the list shipped with the agent (defaults/prices.json, with the month it was checked)

    table = Prices.of_home(home, settings)
    price = table.of("claude-opus-5-5")        # Price(4.0, 20.0, 0.2, 5.0, origin="default", date="2026-11")
    price.cost(usage)                           # USD of one call
    price.label                                 # "default of 2026-11"

A model none of them knows has no price: its calls count 0 and the interface says so. A dated id
(claude-sonnet-4-6-20260101) takes the price of the longest known id it starts with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

FETCHED = "prices.json"  # in the agent's home, written by `vault-watch prices update`
RATES = ("input", "output", "cache_read", "cache_write")
ORIGINS = ("set", "fetched", "default")


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float
    origin: str  # set | fetched | default
    date: str = ""  # when the list was fetched or checked ("2026-11", "2026-11-18"); "" for a price the user set

    @property
    def label(self) -> str:
        """Where the price comes from, for the interface and the journal."""
        if self.origin == "set":
            return "set in the Settings"
        return f"{self.origin} of {self.date}" if self.date else self.origin

    def rates(self) -> dict:
        return {r: getattr(self, r) for r in RATES}

    def cost(self, usage: dict, web_search_usd: float = 0.0) -> float:
        """USD of one call from its usage (tokens of each kind, web searches)."""
        tokens = (usage.get("input", 0) * self.input + usage.get("output", 0) * self.output
                  + usage.get("cache_read", 0) * self.cache_read + usage.get("cache_write", 0) * self.cache_write)
        return tokens / 1e6 + usage.get("web_searches", 0) * web_search_usd


def _defaults() -> dict:
    return json.loads(resources.files("vault_watch_agent").joinpath("defaults/prices.json").read_text(encoding="utf-8"))


def check_rates(value, where: str) -> dict:
    """{input, output, cache_read, cache_write} as non-negative numbers, or ValueError naming `where`."""
    if not isinstance(value, dict) or set(value) != set(RATES):
        raise ValueError(f"{where}: give {', '.join(RATES)} (USD per million tokens)")
    out = {}
    for r in RATES:
        v = value[r]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"{where}.{r}: a number of USD per million tokens, 0 or more")
        out[r] = float(v)
    return out


class Prices:
    """The price table the agent uses: the user's prices, then the fetched list, then the defaults."""

    def __init__(self, set_: dict | None = None, fetched: dict | None = None, defaults: dict | None = None):
        defaults = defaults if defaults is not None else _defaults()
        self.web_search_usd = float(defaults.get("web_search_usd", 0.0))
        self.sources: list[tuple[str, str, dict]] = [
            ("set", "", set_ or {}),
            ("fetched", (fetched or {}).get("date", ""), (fetched or {}).get("models", {})),
            ("default", defaults.get("date", ""), defaults.get("models", {})),
        ]

    @classmethod
    def of_home(cls, home: Path | None, settings: dict | None = None) -> Prices:
        """The table of a user: their settings' `prices`, the list fetched into `home` (when there is one)."""
        fetched = None
        if home is not None and (home / FETCHED).is_file():
            try:
                fetched = json.loads((home / FETCHED).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                fetched = None  # a damaged list is ignored: the defaults apply, never a wrong price
        return cls((settings or {}).get("prices") or {}, fetched)

    def of(self, model: str) -> Price | None:
        for origin, date, table in self.sources:
            rates = table.get(model) or next(
                (table[k] for k in sorted(table, key=len, reverse=True) if model.startswith(k + "-")), None)
            if rates:
                return Price(**{r: float(rates[r]) for r in RATES}, origin=origin, date=date)
        return None

    def cost(self, usage: dict) -> tuple[float, Price | None]:
        """USD of one call and the price it was counted at (None: a model without a price, counted 0)."""
        price = self.of(usage["model"])
        return (price.cost(usage, self.web_search_usd) if price else 0.0), price

    def known(self) -> list[str]:
        """Every model id some source prices."""
        return sorted({m for _, _, table in self.sources for m in table})


# -- the fetched list (T2.2) ----------------------------------------------------------------------------------
LITELLM = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PROVIDERS = ("anthropic",)  # the providers whose models the agent calls


def parse_litellm(data: dict, today: str) -> dict:
    """LiteLLM's public list (USD per token) as a fetched list of this agent (USD per million tokens): the models
    of PROVIDERS that have an input and an output price; a missing cache price is taken as 0.1 x and 1.25 x input,
    and said so in `estimated`."""
    models, estimated = {}, []
    for name, entry in data.items():
        if not isinstance(entry, dict) or entry.get("litellm_provider") not in PROVIDERS or not name.startswith("claude-"):
            continue
        try:
            p_in, p_out = float(entry["input_cost_per_token"]) * 1e6, float(entry["output_cost_per_token"]) * 1e6
        except (KeyError, TypeError, ValueError):
            continue
        read, write = entry.get("cache_read_input_token_cost"), entry.get("cache_creation_input_token_cost")
        if read is None or write is None:
            estimated.append(name)
        models[name] = {"input": round(p_in, 6), "output": round(p_out, 6),
                        "cache_read": round(float(read) * 1e6 if read is not None else p_in * 0.1, 6),
                        "cache_write": round(float(write) * 1e6 if write is not None else p_in * 1.25, 6)}
    return {"date": today, "source": LITELLM, "models": dict(sorted(models.items())), "estimated": sorted(estimated)}


def fetch(today: str, url: str = LITELLM, timeout: int = 30) -> dict:
    """Reads the public list; ValueError when it cannot be read or holds no model of PROVIDERS."""
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "vault-watch-agent"}),
                                    timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"the price list could not be read ({type(e).__name__}: {e})") from e
    fetched = parse_litellm(data, today)
    if not fetched["models"]:
        raise ValueError("the price list holds no Claude model: nothing replaced")
    return fetched


def diff(before: Prices, fetched: dict) -> list[str]:
    """What replacing the cached list with `fetched` changes, for the models priced today and the new ones."""
    lines = []
    for model, rates in fetched["models"].items():
        old = before.of(model)
        if old is None:
            lines.append(f"+ {model}: {_rates(rates)} (new)")
        elif old.origin != "set" and old.rates() != rates:
            lines.append(f"~ {model}: {_rates(old.rates())} ({old.label}) -> {_rates(rates)}")
    current = {m for _, _, table in before.sources[1:2] for m in table}
    lines += [f"- {m}: no longer in the list (the default applies again, if any)" for m in sorted(current - set(fetched["models"]))]
    return lines


def save(home: Path, fetched: dict) -> Path:
    import os

    home.mkdir(parents=True, exist_ok=True)
    partial = home / (FETCHED + ".partial")
    partial.write_text(json.dumps(fetched, indent=1) + "\n", encoding="utf-8")
    os.replace(partial, home / FETCHED)
    return home / FETCHED


def _rates(r: dict) -> str:
    return " / ".join(f"{r[k]:g}" for k in RATES)
