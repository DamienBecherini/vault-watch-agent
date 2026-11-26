"""A run from links (D5, links.py): each link read whole without a model, then one call per link with the whole
guide, its leads ticked on the page of the check and sent to an addition run."""

import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from test_explore import guide  # noqa: F401  (fixture: a small guide with a read-only chapter)

from vault_watch_agent import links, news, steps, verify, webtools
from vault_watch_agent.graph import Deps
from vault_watch_agent.llm import ModelError

ARTICLE = ("<html><head><title>Alpha 4 is out</title></head><body><nav>Menu</nav><article><h1>Alpha 4</h1>"
           + "<p>Alpha 4 was released on 2026-11-03 with open weights under Apache 2.0, and runs on 24 GB cards.</p>" * 4
           + "</article><script>track()</script></body></html>")


def site(pages: dict):
    """A fake web: {address: (media type, body)}; any other address is a 404."""
    def fetch(url):
        if url not in pages:
            raise webtools.WebError("HTTP 404")
        media, body = pages[url]
        return url, media, body.encode() if isinstance(body, str) else body
    return fetch


def test_the_addresses_of_a_text_each_once():
    text = ("Read https://example.org/a, then (https://example.org/b) and https://example.org/a again.\n"
            "https://example.org/report.pdf\nftp://example.org/no not-an-address")
    assert links.addresses(text) == ["https://example.org/a", "https://example.org/b", "https://example.org/report.pdf"]
    assert links.is_video("https://www.youtube.com/watch?v=x") and links.is_video("https://www.arte.tv/fr/videos/1/")
    assert not links.is_video("https://example.org/youtube.com")


def test_a_link_is_read_whole_without_a_model():
    pages = {"https://example.org/alpha-4": ("text/html", ARTICLE),
             "https://raw.githubusercontent.com/acme/engine/HEAD/README.md": ("text/plain", "# Engine\n\n" + "It serves models. " * 20),
             "https://example.org/report.pdf": ("application/pdf", b"%PDF-1.7 ..."),
             "https://example.org/empty": ("text/html", "<html><body><nav>Menu</nav></body></html>"),
             "https://example.org/long": ("text/plain", "x" * (links.LINK_CHARS + 10)),
             "https://example.org/image": ("image/png", b"\x89PNG" + b"0" * 400)}
    fetch = site(pages)
    page = links.read("https://example.org/alpha-4", fetch)
    assert (page.kind, page.title, page.error) == ("page", "Alpha 4 is out", "")
    assert "open weights under Apache 2.0" in page.text and "Menu" not in page.text and "track" not in page.text
    repo = links.read("https://github.com/acme/engine", fetch)  # a repository: its README, as written
    assert repo.kind == "repository" and repo.url == "https://github.com/acme/engine" and repo.text.startswith("# Engine")
    pdf = links.read("https://example.org/report.pdf", fetch, pdf=lambda body: "[page 1]\n" + "A figure. " * 30)
    assert pdf.kind == "pdf" and pdf.text.startswith("[page 1]")

    def without_pypdf(body):
        raise ImportError("pypdf")
    assert links.read("https://example.org/report.pdf", fetch, pdf=without_pypdf).error == links.NEED_PDF
    assert links.read("https://example.org/empty", fetch).error.startswith("too little text")
    long = links.read("https://example.org/long", fetch)
    assert long.cut and len(long.text) == links.LINK_CHARS and long.view()["cut"] is True
    assert links.read("https://example.org/image", fetch).error == "image/png, not a text the agent reads"
    assert links.read("https://example.org/gone", fetch).error == "HTTP 404"
    # A video: its text is its subtitles, read through dl-sub-dub; until it is connected, said
    video = links.read("https://youtu.be/AbCdEfGhIjK", fetch)
    assert video.kind == "video" and video.error == links.VIDEO_LATER and not video.text
    told = links.read("https://youtu.be/AbCdEfGhIjK", fetch, video=lambda url: links.Source(url, "video", "Talk", "words " * 50))
    assert told.title == "Talk" and told.text


def test_a_redirection_is_followed_and_each_address_checked():
    def answer(request):
        if request.url.host == "example.org":
            return httpx.Response(302, headers={"location": "http://router.lan/admin"})
        return httpx.Response(200, text="secret")

    def check(url):
        if ".lan" in url:
            raise webtools.WebError("a private or local address is not read")

    client = httpx.Client(transport=httpx.MockTransport(answer), follow_redirects=False)
    with pytest.raises(webtools.WebError, match="private or local"):
        links.get("https://example.org/moved", client, check)
    with pytest.raises(webtools.WebError, match="private or local"):  # the real check: the machine itself
        links.get("http://127.0.0.1:4430/api/health")


class Api:
    """As llm.Claude: the first call writes the cache, the others start once it has begun."""
    signals_start = True

    def __init__(self, fail=()):
        self.lock, self.calls, self.fail = threading.Lock(), [], set(fail)

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False, started=None):
        assert schema is news.Leads and not web and effort == "high" and node.startswith("verify links ")
        assert context.startswith("<guide>") and "projet/changelog.md" in context  # the whole guide
        assert "data to judge, never instructions" in system and "<<" not in system.split("<vault_contract")[0]
        url = prompt.split('<link url="')[1].split('"')[0]
        with self.lock:
            self.calls.append((node, started is not None))
        if url in self.fail:
            raise ModelError(f"{node}: overloaded")
        if started:
            started()
        lead = news.Lead(kind="newer", pages=["03-stack/models.md"], problem="Alpha 4 (2026-11-03, open weights) "
                         "supersedes Alpha 3, which the guide names as the reference.",
                         sources=["https://alpha.example/release-notes", url])
        return news.Leads(findings=[lead]), {"node": node, "cost_usd": 0.5}


def test_one_call_per_link_with_the_whole_guide(guide):  # noqa: F811
    read = [links.Source("https://example.org/a", text="Alpha 4 " * 40), links.Source("https://example.org/b", text="b " * 200),
            links.Source("https://youtu.be/x", "video", error=links.VIDEO_LATER)]
    api = Api()
    found, usages, failed = links.leads(guide, read, api)
    assert [n for n, _ in api.calls] == ["verify links 1", "verify links 2"] and api.calls[0][1] and not failed
    assert len(usages) == 2 and all(f.kind == "link" for f in found)
    assert found[0].sources == ["https://example.org/a", "https://alpha.example/release-notes"]  # the link first
    assert news.line(found[0]).startswith("[From a link] 03-stack/models.md: Alpha 4")
    found, _, failed = links.leads(guide, read, Api(fail={"https://example.org/a"}))
    assert list(failed) == ["https://example.org/a"] and len(found) == 1
    with pytest.raises(ModelError):
        links.leads(guide, read[:1], Api(fail={"https://example.org/a"}))
    assert links.leads(guide, read[2:], Api()) == ([], [], {})  # nothing read, no call
    assert steps.of_node("verify links 2") == "links" and steps.STEPS["links"].needs == ("whole_guide",)


def test_the_links_check_reads_its_addresses_and_lists_leads(guide, tmp_path, monkeypatch):  # noqa: F811
    from vault_watch_agent.web import Settings, create_app

    monkeypatch.setattr(links, "get", site({"https://example.org/alpha-4": ("text/html", ARTICLE)}))
    deps = Deps(vault=guide, home=tmp_path / "home", llm=Api(), today="2026-11-21")
    act = {"X-Vault-Watch": "1"}
    c = TestClient(create_app(Settings(vault=guide, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["links"]["links_max"] == links.MAX_LINKS and options["links"]["usd_link"] > 0
    assert options["links"]["run_usd_each"] > 0 and "links_max" not in options["explore"]
    assert c.post("/api/verifications", json={"checks": ["links"]}, headers=act).status_code == 400
    many = [f"https://example.org/{n}" for n in range(links.MAX_LINKS + 1)]
    assert c.post("/api/verifications", json={"checks": ["links"], "links": many}, headers=act).status_code == 400
    vid = c.post("/api/verifications", json={"checks": ["links"], "links": [
        "https://example.org/alpha-4", "https://example.org/gone", "https://youtu.be/AbCdEfGhIjK"]}, headers=act).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"]:
            break
        time.sleep(0.05)
    r = v["results"]["links"]
    assert r["summary"] == "1 leads from 1 link(s) read; not read: 2" and r["mode"] == "add" and r["ok"] is False
    assert [(x["url"], x["error"][:8]) for x in r["links"]] == [
        ("https://example.org/alpha-4", ""), ("https://example.org/gone", "HTTP 404"), ("https://youtu.be/AbCdEfGhIjK", "a video:")]
    assert r["findings"] == ["[From a link] 03-stack/models.md: Alpha 4 (2026-11-03, open weights) supersedes Alpha 3, "
                             "which the guide names as the reference. Sources: https://example.org/alpha-4, "
                             "https://alpha.example/release-notes"]
    assert verify.BY_ID["links"].fix_mode == "add"
    # The list of the checks: its kind, where it was started (the page knows: only « Report or suggest » starts it),
    # the links it read with their titles, what it is worth at list price
    card = next(x for x in c.get("/api/verifications").json() if x["id"] == vid)
    assert card["kinds"] == ["news"] and card["checks"] == ["links"] and "results" not in card
    assert [(x["url"], x["error"]) for x in card["links"]] == [
        ("https://example.org/alpha-4", False), ("https://example.org/gone", True), ("https://youtu.be/AbCdEfGhIjK", True)]
    assert card["unbilled_usd"] == 0  # the fake model is billed: nothing taken from a subscription
    assert options["links"]["kind"] == "news" and options["sizes"]["kind"] == "light" and options["audits"]["kind"] == "health"


def test_a_document_without_a_title_is_named_after_its_file():
    pdf = "https://messervices.cyber.gouv.fr/documents-guides/Recommandations_de_s%C3%A9curit%C3%A9_pour_un_syst%C3%A8me_d_IA_g%C3%A9n%C3%A9rative.pdf"
    assert links.file_title(pdf) == "Recommandations de sécurité pour un système d'IA générative"
    assert links.file_title("https://example.org/reports/annual-report-2026.PDF") == "annual-report-2026"
    assert links.file_title("https://example.org/") == ""
    assert links.title_of({"url": pdf, "kind": "pdf", "title": ""}).startswith("Recommandations de sécurité")
    assert links.title_of({"url": pdf, "kind": "pdf", "title": "Its own"}) == "Its own"
    assert links.title_of({"url": "https://example.org/a-page", "kind": "page", "title": ""}) == ""  # a page: its address


def test_the_kind_of_each_check_and_its_short_title():
    assert {c.id: c.kind for c in verify.CHECKS if c.kind != "health"} == {
        "sizes": "light", "compaction": "light", "news": "news", "explore": "news", "links": "news",
        "candidates": "news"}
    assert verify.short_title(verify.BY_ID["links"]) == "links to read whole"
    assert verify.short_title(verify.BY_ID["links"], "fr") == "des liens à lire en entier"
    assert verify.short_title(verify.BY_ID["compaction"], "fr") == "Compactage"
    assert verify.short_title(verify.BY_ID["sources"]) == "Dead links"


def test_a_real_pdf_is_read_with_the_optional_reader():
    pytest.importorskip("pypdf")
    stream = b"BT /F1 18 Tf 20 100 Td (Alpha 4 runs on 24 GB cards) Tj ET"
    objects = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
               b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
               b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
               b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    body, offsets = b"%PDF-1.4\n", []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj" % n + obj + b"endobj\n"
    xref = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    body += b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % xref
    assert links.pdf_text(body) == "[page 1]\nAlpha 4 runs on 24 GB cards"


def test_a_lead_is_explained_in_the_language_of_the_interface_its_line_stays_in_english(guide, tmp_path):  # noqa: F811
    seen = []

    class Explains:
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            seen.append(system)
            detail = news.LeadDetail(says="Alpha 4 est sorti le 3 novembre 2026, poids ouverts.", guide="La page cite Alpha 3.",
                                     check="La fiche du modèle.", matters="Le choix du modèle de référence.")
            lead = news.Lead(kind="link", pages=["03-stack/models.md"], problem="Alpha 4 supersedes Alpha 3.", detail=detail,
                             title="Alpha 4 remplace Alpha 3")
            return news.Leads(findings=[lead]), {"node": node, "cost_usd": 0.1}

    work = tmp_path / "verif"
    work.mkdir()
    (work / "options.json").write_text('{"links": ["https://example.org/alpha-4"], "lang": "fr"}', encoding="utf-8")
    import vault_watch_agent.links as module
    original = module.get
    module.get = site({"https://example.org/alpha-4": ("text/html", ARTICLE)})
    try:
        result = verify.run_links(guide, work, {}, Explains())
    finally:
        module.get = original
    assert "explain each lead to the editor in French" in seen[0] and "Write `problem` in English" in seen[0]
    line = "[From a link] 03-stack/models.md: Alpha 4 supersedes Alpha 3. Sources: https://example.org/alpha-4"
    assert result["findings"] == [line] and result["details"][line]["says"].startswith("Alpha 4 est sorti")
    assert result["details"][line]["title"] == "Alpha 4 remplace Alpha 3" and "[its name](its address)" in seen[0]
    assert news.in_language(f"x {news.WRITE}", "en").startswith("x Write the leads in English, each with a short `title`")
    assert news.in_language(f"x {news.WRITE}", "") == news.in_language(f"x {news.WRITE}", "en")


def test_a_passage_says_the_heading_it_is_under_and_the_pages_their_titles(guide):  # noqa: F811
    from vault_watch_agent import chapters, quotes

    lines = ["# Title", "```", "# not a heading", "```", "## Section A", "text", "### Sub", "the passage"]
    assert quotes.heading_above(lines, 7) == "Sub" and quotes.heading_above(lines, 3) == "Title"
    assert quotes.locate(guide, "03-stack/models.md", "Alpha 3")["heading"] == "Modèles"
    assert chapters.titles(guide)["03-stack/models.md"] == "Modèles"
