"""Builds a standalone HTML copy of each Markdown page of docs/, for reading a downloaded copy of the repository.

GitHub renders the Markdown and its Mermaid diagrams; a local Markdown viewer usually does not. The HTML copies need
nothing to display: each diagram is drawn once, at build time, as an SVG embedded in the page, in a light and a dark
version (the page shows the one matching the system theme). No script, no CDN, readable offline.

The Markdown files stay the source: edit them, then run

    python docs/build_html.py

Needs the dev extra (`pip install -e ".[dev]"`), Chrome or Chromium (headless, to run Mermaid; set CHROME to its path
if it is not found) and an internet connection while building (Mermaid is loaded from a CDN by the build only).
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
GITHUB = "https://github.com/DamienBecherini/vault-watch-agent/blob/main/"
THEMES = {"light": "default", "dark": "dark"}

STYLE = """
:root { --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0; --soft: #f6f8fa; --accent: #0969da;
  --font: -apple-system, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", Consolas, monospace; }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #3d444d;
  --soft: #151b23; --accent: #4493f8; color-scheme: dark; } }
body { background: var(--bg); color: var(--fg); font: 16px/1.5 var(--font); margin: 0; padding: 0 16px 48px; }
main { max-width: 980px; margin: 0 auto; }
h1, h2 { border-bottom: 1px solid var(--line); padding-bottom: .3em; }
h2 { margin-top: 1.6em; }
a { color: var(--accent); }
code { font-family: var(--mono); font-size: 85%; background: var(--soft); padding: .2em .4em; border-radius: 6px; }
pre code { background: none; padding: 0; }
pre { background: var(--soft); padding: 16px; border-radius: 6px; overflow-x: auto; }
.diagram { overflow-x: auto; margin: 16px 0; padding: 8px; border: 1px solid var(--line); border-radius: 6px; text-align: center; }
.diagram svg { max-width: 100%; height: auto; }
.diagram .dark { display: none; }
@media (prefers-color-scheme: dark) { .diagram .light { display: none; } .diagram .dark { display: block; } }
table { border-collapse: collapse; margin: 16px 0; display: block; overflow-x: auto; max-width: 100%; }
th, td { border: 1px solid var(--line); padding: 6px 13px; vertical-align: top; }
tr:nth-child(2n) td { background: var(--soft); }
hr { border: 0; border-top: 1px solid var(--line); margin: 24px 0; }
"""

# Page run by headless Chrome: renders every diagram in both themes and writes the SVGs, as JSON, into the DOM.
RENDER_PAGE = """<!doctype html><meta charset="utf-8"><body><pre id="result"></pre>
<script src="%s"></script>
<script>
(async () => {
  const sources = %s, themes = %s, out = {};
  for (const [name, theme] of Object.entries(themes)) {
    mermaid.initialize({ startOnLoad: false, theme });
    out[name] = [];
    for (let i = 0; i < sources.length; i++) {
      try { out[name].push((await mermaid.render(`d${i}-${name}`, sources[i])).svg); }
      catch (e) { out[name].push("ERROR: " + e.message); }
    }
  }
  document.getElementById("result").textContent = JSON.stringify(out);
})();
</script>"""


def chrome() -> str:
    candidates = [os.environ.get("CHROME", ""), "chrome", "google-chrome", "chromium", "chromium-browser",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for c in candidates:
        if c and (Path(c).is_file() or shutil.which(c)):
            return shutil.which(c) or c
    raise SystemExit("Chrome or Chromium not found: set CHROME to its path.")


def render_diagrams(sources: list[str]) -> dict[str, list[str]]:
    """SVG of each Mermaid source, per theme, drawn by Mermaid in headless Chrome."""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "render.html"
        page.write_text(RENDER_PAGE % (MERMAID, json.dumps(sources), json.dumps(THEMES)), encoding="utf-8")
        dom = subprocess.run(
            [chrome(), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={tmp}/profile",
             "--virtual-time-budget=30000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    if not found or not found.group(1):
        raise SystemExit("Mermaid did not render (no internet connection to load it?).")
    svgs = json.loads(html.unescape(found.group(1)))
    errors = [s for t in svgs.values() for s in t if s.startswith("ERROR")]
    if errors:
        raise SystemExit("Mermaid syntax error:\n" + "\n".join(errors))
    return svgs


def link(match: re.Match) -> str:
    target = match.group(1)
    if re.match(r"[a-z]+:|#", target):
        return match.group(0)
    path, _, anchor = target.partition("#")
    if "/" not in path and path.endswith(".md"):  # another page of docs/: its HTML copy
        path = path[:-3] + ".html"
    else:  # README, sources, metrics: the GitHub page, readable without a Markdown viewer
        path = GITHUB + str((DOCS / path).resolve().relative_to(DOCS.parent)).replace("\\", "/")
    return f'href="{path}{"#" + anchor if anchor else ""}"'


def build(source: Path) -> Path:
    text = source.read_text(encoding="utf-8")
    diagrams = []

    def keep(m: re.Match) -> str:
        diagrams.append(m.group(1))
        return f"\n\nMERMAID{len(diagrams) - 1}\n\n"

    text = re.sub(r"```mermaid\n(.*?)```", keep, text, flags=re.S)
    text = text.replace('<div align="center">', '<div align="center" markdown="1">')
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "md_in_html"])
    svgs = render_diagrams(diagrams) if diagrams else {}
    for i in range(len(diagrams)):
        figure = "".join(f'<div class="{name}">{svgs[name][i]}</div>' for name in THEMES)
        body = body.replace(f"<p>MERMAID{i}</p>", f'<div class="diagram">{figure}</div>')
    body = re.sub(r'href="([^"]+)"', link, body)
    title = re.sub(r"<[^>]+>", "", re.search(r"<h1[^>]*>(.*?)</h1>", body).group(1))
    lang = "fr" if source.stem.endswith(".fr") else "en"
    page = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<!-- Generated from {source.name} by docs/build_html.py: edit the Markdown, then rebuild. -->
<style>{STYLE}</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""
    out = source.with_suffix(".html")
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    for md in sorted(DOCS.glob("*.md")):
        print(build(md).name)
