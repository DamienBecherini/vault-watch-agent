"""Web search and page reading for the engines whose model has no web of its own (the OpenAI-compatible one).

The code runs them, not the model: the model asks for a search or a page by a tool call, the agent does the request,
follows the redirections itself, keeps to public addresses, cuts what it hands back, and counts.

    tools = WebTools(searxng="http://searx.lan:8080")
    tools.search("vLLM 0.33 release notes")        # plain text: numbered results, title, address, snippet
    tools.fetch("https://github.com/vllm-project/vllm/releases/tag/v0.33.1")   # "Source: …" then the readable text
    budget = Budget()                               # 20 searches and 30 pages per call, as the API engine's tools
    budget.run(tools, "web_search", {"query": "…"})  # what a tool call returns to the model, limits included

Search goes through a SearXNG instance (self-hosted, no key, its JSON output switched on); without one, only pages
are read. A page is plain text extracted from its HTML, at most MAX_CHARS characters.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from . import __version__

MAX_SEARCHES = 20  # per model call, as the API engine's web_search max_uses
MAX_PAGES = 30     # per model call, as its web_fetch max_uses
MAX_BYTES = 3_000_000
MAX_CHARS = 30_000
MAX_REDIRECTS = 5
RESULTS = 8
TIMEOUT = 30
UA = f"vault-watch-agent/{__version__} (+https://github.com/DamienBecherini/vault-watch-agent)"

# The tools as the model sees them (OpenAI function calling).
SEARCH_TOOL = {"type": "function", "function": {
    "name": "web_search", "description": "Search the web. Returns numbered results: title, address, snippet, date.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The search"}},
                   "required": ["query"]}}}
FETCH_TOOL = {"type": "function", "function": {
    "name": "web_fetch", "description": "Read a web page (or a text, JSON or Markdown file) as plain text, with its "
                                        "final address. Use it to check a fact on its primary source.",
    "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "http or https address"}},
                   "required": ["url"]}}}


class WebError(RuntimeError):
    """A search or a page that could not be read; the message goes back to the model, which can try another."""


def public(url: str) -> None:
    """WebError unless `url` is http(s) to a public address: a page must not make the agent read its own machine or
    the local network (the interface on 127.0.0.1, a router, a cloud metadata address)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError(f"{url}: only http and https addresses are read")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise WebError(f"{parts.hostname}: unknown host") from e
    for info in infos:
        if not is_public(str(info[4][0])):
            raise WebError(f"{parts.hostname}: a private or local address is not read")


NAT64 = ipaddress.ip_network("64:ff9b::/96")


def is_public(address: str) -> bool:
    """Whether an IP address is on the public Internet, an IPv6 address that carries an IPv4 one (NAT64, 6to4,
    Teredo, mapped) judged by that IPv4 one: « 64:ff9b::c0a8:101 » is 192.168.1.1."""
    ip = ipaddress.ip_address(str(address).split("%")[0])
    if not ip.is_global:
        return False
    if ip.version == 6:
        inner = [ip.ipv4_mapped, ip.sixtofour, ip.teredo[1] if ip.teredo else None,
                 ipaddress.IPv4Address(ip.packed[-4:]) if ip in NAT64 else None]
        return all(v4 is None or v4.is_global for v4 in inner)
    return True


def connected_public(response: httpx.Response) -> None:
    """WebError unless the address the request actually reached is public: a name can answer a public address when
    it is checked and a private one when the connection is made (DNS rebinding). Called once the headers are in,
    before the body is read; a response without a network stream (a test's fake transport) is let through."""
    stream = response.extensions.get("network_stream")
    peer = stream.get_extra_info("server_addr") if stream is not None else None
    if peer and not is_public(peer[0]):
        raise WebError(f"{response.url.host}: answered from a private or local address, not read")


class _Text(HTMLParser):
    """The readable text of a page: headings, paragraphs, lists, tables and code; not scripts, styles, menus."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "template", "iframe", "button"}
    BLOCK = {"p", "div", "section", "article", "main", "li", "tr", "br", "pre", "blockquote", "h1", "h2", "h3", "h4",
             "h5", "h6", "table", "ul", "ol", "dt", "dd", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.out.append("\n")
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.out.append("#" * int(tag[1]) + " ")
            elif tag == "li":
                self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)

    def text(self) -> str:
        lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(self.out).split("\n"))
        # Items, headings and cells left empty (menus of icons, as on GitHub) are dropped: they eat the page's budget.
        kept = (line for line in lines if not re.fullmatch(r"(#+|-|\|)( \|)*", line))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def readable(html: str) -> tuple[str, str]:
    """(title, text) of an HTML page."""
    p = _Text()
    p.feed(html)
    p.close()
    return p.title.strip(), p.text()


class WebTools:
    def __init__(self, searxng: str = "", client: httpx.Client | None = None, check_address=public):
        self.searxng = searxng.rstrip("/")
        self.client = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=False)
        self.check_address = check_address  # the tests read fake pages on fake hosts

    @property
    def can_search(self) -> bool:
        return bool(self.searxng)

    def search(self, query: str) -> str:
        if not self.searxng:
            raise WebError("no search engine is set (Settings: the SearXNG address); read pages by their address")
        query = str(query or "").strip()
        if not query:
            raise WebError("an empty search")
        try:
            r = self.client.get(f"{self.searxng}/search", params={"q": query, "format": "json"})
        except httpx.HTTPError as e:
            raise WebError(f"the search engine could not be reached ({type(e).__name__})") from e
        if r.status_code == 403:
            raise WebError("the SearXNG instance refuses JSON: add json to search.formats in its settings.yml")
        if r.status_code != 200:
            raise WebError(f"the search engine answered HTTP {r.status_code}")
        try:
            results = r.json().get("results") or []
        except ValueError as e:
            raise WebError("the search engine did not answer JSON") from e
        if not results:
            return f"No result for: {query}"
        lines = []
        for n, item in enumerate(results[:RESULTS], start=1):
            date = f" ({str(item['publishedDate'])[:10]})" if item.get("publishedDate") else ""
            snippet = re.sub(r"\s+", " ", str(item.get("content") or ""))[:400]  # not in the f-string: Python 3.11
            lines.append(f"{n}. {item.get('title') or '(no title)'}{date}\n   {item.get('url')}\n   {snippet}")
        return "\n".join(lines)

    def fetch(self, url: str) -> str:
        """"Source: <final address>" then the page's text, at most MAX_CHARS characters."""
        url = str(url or "").strip()
        for _ in range(MAX_REDIRECTS + 1):
            self.check_address(url)
            try:
                with self.client.stream("GET", url) as r:
                    if self.check_address is public:
                        connected_public(r)
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("location", ""))
                        continue
                    if r.status_code != 200:
                        raise WebError(f"{url}: HTTP {r.status_code}")
                    kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    body = b""
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    charset = r.charset_encoding or "utf-8"
            except httpx.HTTPError as e:
                raise WebError(f"{url}: could not be read ({type(e).__name__})") from e
            break
        else:
            raise WebError(f"{url}: more than {MAX_REDIRECTS} redirections")
        if kind == "application/pdf" or body[:5] == b"%PDF-":
            raise WebError(f"{url}: a PDF, not read; look for the same fact on an HTML page")
        text = body.decode(charset, errors="replace")
        title = ""
        if "html" in kind or (not kind and "<html" in text[:2000].lower()):
            title, text = readable(text)
        elif kind == "application/json":
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
            except ValueError:
                pass
        elif kind and not kind.startswith("text/") and kind not in ("application/xml", "application/rss+xml",
                                                                     "application/atom+xml"):
            raise WebError(f"{url}: {kind}, not a text the agent reads")
        cut = len(text) > MAX_CHARS
        head = f"Source: {url}\n" + (f"Title: {title}\n" if title else "")
        return head + "\n" + text[:MAX_CHARS] + (f"\n\n[cut at {MAX_CHARS} characters]" if cut else "")


@dataclass
class Budget:
    """What one model call may still do on the web, and what it did (the journal counts the searches)."""
    searches: int = 0
    pages: int = 0
    max_searches: int = MAX_SEARCHES
    max_pages: int = MAX_PAGES

    def run(self, tools: WebTools, name: str, arguments: dict) -> str:
        """The text a tool call returns to the model: the result, or why there is none (never an exception)."""
        try:
            if name == "web_search":
                if self.searches >= self.max_searches:
                    return f"Limit reached: {self.max_searches} searches in this answer. Answer with what you found."
                self.searches += 1
                return tools.search(arguments.get("query", ""))
            if name == "web_fetch":
                if self.pages >= self.max_pages:
                    return f"Limit reached: {self.max_pages} pages in this answer. Answer with what you read."
                self.pages += 1
                return tools.fetch(arguments.get("url", ""))
            return f"Unknown tool {name}: use web_search or web_fetch."
        except WebError as e:
            return f"Error: {e}"

    def tools(self, web: WebTools) -> list[dict]:
        return [SEARCH_TOOL, FETCH_TOOL] if web.can_search else [FETCH_TOOL]
