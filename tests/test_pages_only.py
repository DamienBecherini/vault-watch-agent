"""A correction touches a content page of the guide or its mirror, never another file (vault.is_page): what a model
writes as the page of a correction comes from what it read, and the agent runs the guide's scripts after applying."""

import pytest
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent import vault


@pytest.mark.parametrize("page", [
    "scripts/audit-freshness.mjs",          # a script the agent runs at the audits step
    "vault-watch.toml", "package.json",     # the manifest, what npm runs
    ".agents/skills/vault-watch/brief.md",  # a dot folder: tooling
    "../outside.md", "03-stack/../../outside.md", "C:outside.md", "C:/Windows/win.ini", "/etc/passwd",
    "03-stack\\engines.md", "03-stack/engines.txt", "", "03-stack//engines.md",
])
def test_what_is_not_a_page_of_the_guide_is_never_touched(setup, page):  # noqa: F811
    deps, _, _ = setup
    assert not vault.is_page(deps.vault, page)
    assert vault.check(deps.vault, page, "x") == "not-a-page"
    with pytest.raises(ValueError, match="not a page"):
        vault.apply(deps.vault, page, "x", "y", "2026-11-22")


def test_a_page_and_its_mirror_are_pages(setup):  # noqa: F811
    deps, _, _ = setup
    assert vault.is_page(deps.vault, "03-stack/engines.md")
    assert vault.is_page(deps.vault, "en/03-stack/engines.md")
    assert not vault.is_page(deps.vault, "03-stack/missing.md")  # not a page yet: an addition never creates one
    assert vault.check(deps.vault, "03-stack/missing.md", "x") == "page-not-found"
