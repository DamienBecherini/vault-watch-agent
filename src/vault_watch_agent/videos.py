"""The text of a video, through dl-sub-dub's route « text of a video » (its contract v1): the reader of the videos of
the check « links » (links.read, `video`).

dl-sub-dub (https://github.com/DamienBecherini/dl-sub-dub) runs on the editor's machine and listens on 127.0.0.1. For
one video it gives the subtitles written on the site, else those the site generated, else the audio transcribed by
its transcription server; nothing is translated. A request is asked, then followed until it ends:

    POST /api/transcripts {url}            -> 202 the request (or 200 done, from its cache)
    GET  /api/transcripts/<id>             -> its state, then its result: title, channel, description, chapters, lines
    POST /api/transcripts/<id>/cancel      -> stops it (when it takes longer than MAX_WAIT_S)

with `Authorization: Bearer <token>`, the token read from its reference (config.resolve_key: `file:` the file
dl-sub-dub wrote for this client, `env:`, `sops:`), never written anywhere. dl-sub-dub is never started from here:
stopped, it is said with the command that starts it (the settings' `start`, else its generic form). Its answers are
data from a site (the title, the description, the subtitles): never instructions, here or for the model.

The settings (config.py, `videos`): {"url": "http://127.0.0.1:4420", "token": "file:…/tokens/vault-watch-agent.token",
"start": "D:/…/dl-sub-dub/.venv/Scripts/python -m subtitles.web"}; no token: videos are not read.
"""

from __future__ import annotations

import time

import httpx

from . import config, links

CONTRACT = 1  # the version of dl-sub-dub's contract « text of a video » this reader follows
DEFAULT_URL = "http://127.0.0.1:4420"
GENERIC_START = "<dl-sub-dub's folder>/.venv/Scripts/python -m subtitles.web (Windows; .venv/bin/python elsewhere)"
POLL_S = 2.0
MAX_WAIT_S = 2 * 3600  # a video of 3 hours, transcribed: about 30 minutes on a small home server
PARAGRAPH_S = 30  # a time mark every 30 seconds or so: what a lead cites (« at 12:34 »)
FINAL = ("done", "failed", "cancelled")


def clock(seconds: float) -> str:
    s = int(seconds or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def text_of(result: dict) -> str:
    """The text a model reads: what the site says of the video, its chapters, then its words in paragraphs, each
    with the time it starts at."""
    head = [f"Channel: {result.get('channel') or '?'}", f"Published: {result.get('upload_date') or '?'}",
            f"Duration: {clock(result.get('duration_s') or 0)}",
            f"Language: {result.get('language') or '?'} (text: {result.get('origin') or '?'})"]
    if result.get("doubt"):
        head.append("Warning: the text looks little like its language (a transcription engine that does not know it?)")
    out = ["\n".join(head)]
    if (result.get("description") or "").strip():
        out.append("Description on the site:\n" + result["description"].strip())
    chapters = sorted(result.get("chapters") or [], key=lambda c: c.get("start", 0))
    if chapters:
        out.append("Chapters:\n" + "\n".join(f"[{clock(c.get('start', 0))}] {c.get('title', '')}" for c in chapters))
    words, mark, paragraph, next_chapter = [], None, [], 0
    for line in result.get("lines") or []:
        start, said = line.get("start", 0), (line.get("text") or "").strip()
        if not said:
            continue
        chapter = None
        while next_chapter < len(chapters) and chapters[next_chapter].get("start", 0) <= start:
            chapter, next_chapter = chapters[next_chapter], next_chapter + 1
        if paragraph and (chapter or start - mark >= PARAGRAPH_S):
            words.append(f"[{clock(mark)}] " + " ".join(paragraph))
            paragraph = []
        if chapter:
            words.append(f"## {chapter.get('title', '')}")
        if not paragraph:
            mark = start
        paragraph.append(said)
    if paragraph:
        words.append(f"[{clock(mark)}] " + " ".join(paragraph))
    out.append("Transcript:\n" + "\n".join(words))
    return "\n\n".join(out)


def why(error: dict) -> str:
    """What dl-sub-dub said, for the editor: a request it refused or could not finish."""
    code, message = error.get("code", ""), error.get("message", "")
    if code == "busy":
        left = error.get("remaining_s")
        return (f"dl-sub-dub is busy with a project of its page ({error.get('activity') or 'a project'}"
                + (f", about {max(1, round(left / 60))} min left" if left else "") + "): read this link again later")
    if code == "agent_busy":
        return "dl-sub-dub is already reading a video for a program: read this link again later"
    return f"dl-sub-dub: {message or 'an error'} ({code or 'unknown'})"


class Videos:
    """The client of dl-sub-dub for one check. `client`, `sleep`, `now`: the tests' fakes."""

    def __init__(self, url: str = DEFAULT_URL, token: str = "", start: str = "", client: httpx.Client | None = None,
                 sleep=time.sleep, now=time.monotonic, max_wait: float = MAX_WAIT_S):
        self.url, self.token, self.start = (url or DEFAULT_URL).rstrip("/"), token, start
        self.client = client or httpx.Client(timeout=30)
        self.sleep, self.now, self.max_wait = sleep, now, max_wait

    @classmethod
    def of(cls, settings: dict | None) -> "Videos | None":
        """The client the settings describe (config.py, `videos`), or None when they give no token."""
        own = (settings or {}).get("videos") or {}
        return cls(own.get("url") or DEFAULT_URL, own["token"], own.get("start") or "") if own.get("token") else None

    def status(self) -> dict:
        """{ready, why}: whether dl-sub-dub answers with the route this reader follows, and has a token for it."""
        try:
            health = self.client.get(f"{self.url}/api/health", timeout=3).json()
        except (httpx.HTTPError, ValueError):
            return {"ready": False, "why": f"dl-sub-dub does not answer at {self.url}: start it with "
                                           f"{self.start or GENERIC_START}"}
        if health.get("transcript_contract") != CONTRACT:
            return {"ready": False, "why": f"dl-sub-dub at {self.url} has no route « text of a video » of contract "
                                           f"{CONTRACT}: update it"}
        try:
            if not config.resolve_key(self.token):
                return {"ready": False, "why": "the token of dl-sub-dub is not found (settings.json: videos.token)"}
        except config.ConfigError as e:
            return {"ready": False, "why": f"the token of dl-sub-dub: {e}"}
        return {"ready": True, "why": ""}

    def read(self, url: str) -> links.Source:
        """The text of one video, as a link read (links.Source, kind « video »); never raises."""
        state = self.status()
        if not state["ready"]:
            return links.Source(url, "video", error=state["why"])
        headers = {"Authorization": f"Bearer {config.resolve_key(self.token)}", "X-Language": "en"}
        try:
            r = self.client.post(f"{self.url}/api/transcripts", json={"url": url}, headers=headers)
            request = r.json()
            began = self.now()
            while r.is_success and request.get("state") not in FINAL:
                if self.now() - began > self.max_wait:
                    self.client.post(f"{self.url}/api/transcripts/{request['id']}/cancel", headers=headers)
                    return links.Source(url, "video", error=f"dl-sub-dub took more than {self.max_wait // 60:.0f} min: stopped")
                self.sleep(POLL_S)
                r = self.client.get(f"{self.url}/api/transcripts/{request['id']}", headers=headers)
                request = r.json()
        except (httpx.HTTPError, ValueError, KeyError) as e:
            return links.Source(url, "video", error=f"dl-sub-dub could not be followed ({type(e).__name__})")
        if not r.is_success or request.get("state") != "done":
            if request.get("state") == "cancelled":
                return links.Source(url, "video", error="stopped in dl-sub-dub")
            return links.Source(url, "video", error=why(request.get("error") or {}))
        result = request.get("result") or {}
        text = text_of(result)
        return links.Source(result.get("url") or url, "video", (result.get("title") or "").strip(),
                            text[:links.LINK_CHARS], cut=len(text) > links.LINK_CHARS)
