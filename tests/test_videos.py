"""The text of a video through dl-sub-dub's route « text of a video » (contract v1, videos.py), against a fake
dl-sub-dub that answers as the contract says."""

import json

import httpx
import pytest

from vault_watch_agent import config, links, verify, videos

RESULT = {
    "url": "https://www.youtube.com/watch?v=AbCdEfGhIjK", "site": "youtube", "video_id": "AbCdEfGhIjK",
    "title": "Alpha 4 on a 24 GB card", "channel": "A channel", "upload_date": "2026-11-10", "duration_s": 754.0,
    "description": "Sources: https://alpha.example/release-notes", "chapters": [{"start": 0, "title": "Intro"},
                                                                              {"start": 60, "title": "Benchmarks"}],
    "language": "en", "language_from": "site", "origin": "auto", "doubt": None, "fetched_at": "2026-11-21T10:00:00+01:00",
    "lines": [{"start": 0.5, "end": 3.0, "text": "Hello."}, {"start": 12.0, "end": 15.0, "text": "Alpha 4 is out."},
              {"start": 40.0, "end": 44.0, "text": "It has open weights."},
              {"start": 61.0, "end": 66.0, "text": "It runs at 40 tokens per second."}],
    "text": "Hello. Alpha 4 is out. It has open weights. It runs at 40 tokens per second.",
}


class DlSubDub:
    """A fake dl-sub-dub: health, then a request that goes through `states` before it ends."""

    def __init__(self, token="s3cret", states=("queued", "transcribing", "done"), health=None, refuse=None, error=None):
        self.token, self.states, self.health, self.refuse, self.error = token, list(states), health, refuse, error
        self.seen, self.cancelled = [], False

    def request(self, state):
        return {"contract": 1, "id": "3f9c2a71b04e", "client": "vault-watch-agent", "state": state,
                "result": RESULT if state == "done" else None, "error": self.error if state == "failed" else None}

    def __call__(self, r: httpx.Request) -> httpx.Response:
        self.seen.append((r.method, r.url.path))
        if r.url.path == "/api/health":
            return httpx.Response(200, json=self.health or {"contract": 2, "transcript_contract": 1})
        assert r.headers["authorization"] == f"Bearer {self.token}"
        if r.method == "POST" and r.url.path == "/api/transcripts":
            assert json.loads(r.content) == {"url": "https://youtu.be/AbCdEfGhIjK"}
            if self.refuse:
                return httpx.Response(self.refuse[0], json={"contract": 1, "error": self.refuse[1]})
            return httpx.Response(202, json=self.request(self.next()))
        if r.url.path.endswith("/cancel"):
            self.cancelled = True
            return httpx.Response(200, json=self.request("cancelled"))
        return httpx.Response(200, json=self.request(self.next()))

    def next(self):
        """The next state; the last one stays."""
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


def reader(fake, tmp_path, max_wait=60, token_file=True):
    token = tmp_path / "vault-watch-agent.token"
    if token_file:
        token.write_text(fake.token + "\n", encoding="utf-8")
    ticks = iter(range(0, 10_000, 10))
    return videos.Videos("http://127.0.0.1:4420", f"file:{token}", "D:/dl-sub-dub/.venv/Scripts/python -m subtitles.web",
                         client=httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda s: None,
                         now=lambda: next(ticks), max_wait=max_wait)


def test_a_video_is_read_through_dl_sub_dub(tmp_path):
    fake = DlSubDub()
    got = reader(fake, tmp_path).read("https://youtu.be/AbCdEfGhIjK")
    assert (got.kind, got.url, got.title, got.error) == ("video", RESULT["url"], "Alpha 4 on a 24 GB card", "")
    assert got.text.startswith("Channel: A channel\nPublished: 2026-11-10\nDuration: 12:34\nLanguage: en (text: auto)")
    assert "Description on the site:\nSources: https://alpha.example/release-notes" in got.text
    assert "Chapters:\n[0:00] Intro\n[1:00] Benchmarks" in got.text
    # Paragraphs of about 30 seconds, a new one at each chapter, each with the time it starts at
    assert got.text.endswith("Transcript:\n## Intro\n[0:00] Hello. Alpha 4 is out.\n[0:40] It has open weights.\n"
                             "## Benchmarks\n[1:01] It runs at 40 tokens per second.")
    assert [m for m, _ in fake.seen].count("GET") == 3  # health, then two polls until done
    assert videos.clock(3725) == "1:02:05"


def test_what_dl_sub_dub_says_when_it_cannot(tmp_path):
    url = "https://youtu.be/AbCdEfGhIjK"
    busy = {"code": "busy", "message": "The machine is busy.", "activity": "video 3/22", "remaining_s": 1260}
    assert reader(DlSubDub(states=("fetching", "failed"), error=busy), tmp_path).read(url).error == (
        "dl-sub-dub is busy with a project of its page (video 3/22, about 21 min left): read this link again later")
    quota = (429, {"code": "quota_exceeded", "message": "Too many requests for this token: try again later.",
                   "retry_after_s": 1740, "limit": 20, "window": "hour"})
    assert reader(DlSubDub(refuse=quota), tmp_path).read(url).error == (
        "dl-sub-dub: Too many requests for this token: try again later. (quota_exceeded)")
    assert "already reading a video" in reader(DlSubDub(refuse=(409, {"code": "agent_busy"})), tmp_path).read(url).error
    slow = DlSubDub(states=("transcribing",))
    assert reader(slow, tmp_path, max_wait=30).read(url).error == "dl-sub-dub took more than 0 min: stopped" and slow.cancelled
    # Not answering, an older dl-sub-dub, no token: said, with what to do
    def down(r):
        raise httpx.ConnectError("refused")
    off = videos.Videos("http://127.0.0.1:4420", "file:x", "", client=httpx.Client(transport=httpx.MockTransport(down)))
    assert off.read(url).error.startswith("dl-sub-dub does not answer at http://127.0.0.1:4420: start it with <dl-sub-dub's")
    old = reader(DlSubDub(health={"contract": 2}), tmp_path).status()
    assert old == {"ready": False, "why": "dl-sub-dub at http://127.0.0.1:4420 has no route « text of a video » of contract 1: update it"}
    missing = reader(DlSubDub(), tmp_path / "nowhere", token_file=False).status()
    assert not missing["ready"] and missing["why"].startswith("the token of dl-sub-dub: key file")


def test_the_settings_name_dl_sub_dub_by_reference(tmp_path):
    assert config.check({})["videos"] == {"url": "", "token": "", "start": ""} and videos.Videos.of(config.check({})) is None
    cfg = config.check({"videos": {"url": "http://127.0.0.1:4420", "token": "file:C:/x/vault-watch-agent.token"}})
    assert videos.Videos.of(cfg).url == "http://127.0.0.1:4420"
    with pytest.raises(config.ConfigError, match="never the token itself"):
        config.check({"videos": {"token": "s3cret"}})
    with pytest.raises(config.ConfigError, match="not a local address"):
        config.check({"videos": {"url": "http://192.168.1.10:4420", "token": "env:T"}})


def test_the_links_check_reads_a_video_with_the_reader_of_the_settings(tmp_path, monkeypatch):
    work = tmp_path / "verif"
    work.mkdir()
    (work / "options.json").write_text(json.dumps({"links": ["https://youtu.be/AbCdEfGhIjK"],
                                                   "videos": {"url": "http://127.0.0.1:4420", "token": "env:T"}}), encoding="utf-8")
    given = {}

    class Reader:
        def read(self, url):
            return links.Source(url, "video", "Talk", error="dl-sub-dub: no (x)")

    monkeypatch.setattr(videos.Videos, "of", classmethod(lambda cls, s: given.update(s) or Reader()))
    result = verify.run_links(tmp_path, work, {}, llm=None)
    assert given == {"videos": {"url": "http://127.0.0.1:4420", "token": "env:T"}}
    assert result["links"] == [{"url": "https://youtu.be/AbCdEfGhIjK", "kind": "video", "title": "Talk", "chars": 0,
                                "cut": False, "error": "dl-sub-dub: no (x)"}]
