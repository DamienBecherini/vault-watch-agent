// @ts-check
/* vault-watch: the passages a run changed, highlighted in a text area (the retouches, the corrections at the publish
   step). */

import { esc } from "./util.js";
import { T } from "./texts.js";

// --- The passages a run changed, highlighted in an editor -----------------------------------------------------------
// A text area cannot colour part of its text: a layer behind it holds the same text, with the same font, padding,
// width and wrapping, its passages in <mark>; the text area, transparent, is typed in as usual (undo, selection,
// spelling). The layer follows its size (the page's zoom, the browser's, a resize), its scrolling and its typing.
// What a passage adds when it only adds (a sentence after a paragraph): that part alone
export const addedPart = (before, after) => after.length > before.length && after.startsWith(before) ? after.slice(before.length) : after;
// Where the passages are in a text: each one whole, else its lines long enough to be found again (a passage typed over)
function passageRanges(text, passages) {
  const found = [];
  for (const p of passages) {
    const whole = String(p || "").trim();
    if (!whole) continue;
    const at = text.indexOf(whole);
    if (at >= 0) { found.push([at, at + whole.length]); continue; }
    for (const line of whole.split("\n").map(l => l.trim()).filter(l => l.length >= 12)) {
      const i = text.indexOf(line);
      if (i >= 0) found.push([i, i + line.length]);
    }
  }
  found.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of found) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1] + 1) last[1] = Math.max(last[1], r[1]); else merged.push([...r]);
  }
  return merged;
}
// Every editor's passages in one highlight of the page (CSS Custom Highlight API), its colour in style.css
const HL_RANGES = new Map();
function hlRefresh() {
  for (const [layer] of HL_RANGES) if (!layer.isConnected) HL_RANGES.delete(layer);  // an editor closed, a page left
  CSS.highlights.set("vw-passage", new Highlight(...[...HL_RANGES.values()].flat()));
}
const HL_COPY = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing", "tabSize",
  "textIndent", "textTransform", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "whiteSpace", "overflowWrap",
  "wordBreak", "direction", "textAlign", "fontVariant", "fontStretch", "fontKerning", "fontFeatureSettings",
  "fontVariationSettings", "hyphens", "textRendering", "lineBreak"];
export function highlightEditor(t, passages, nav) {
  const wrap = document.createElement("div"), back = document.createElement("div");
  back.style.backgroundColor = getComputedStyle(t).backgroundColor;  // read before the text area turns transparent
  wrap.className = "hl-wrap";
  back.className = "hl-back";
  back.setAttribute("aria-hidden", "true");
  if (t.lang) back.lang = t.lang;  // the lines break by the rules of the text's language (French spaces before « : ; ? ! »)
  t.parentNode.insertBefore(wrap, t);
  wrap.append(back, t);
  let list = passages, frame = 0, current = -1;
  const place = () => {
    const cs = getComputedStyle(t);
    HL_COPY.forEach(k => { back.style[k] = cs[k]; });
    // The same box as the text area: its whole width (100% of the wrapper, to the fraction of a pixel), its borders
    // (transparent), its scroll bar when it has one. A box narrower by the bar, even to the pixel, wraps some lines
    // elsewhere than a text area does.
    back.style.top = `${t.offsetTop}px`;
    back.style.left = `${t.offsetLeft}px`;
    back.style.width = "100%";
    back.style.height = `${t.offsetHeight}px`;
    back.style.borderStyle = "solid";
    back.style.borderColor = "transparent";
    ["Top", "Right", "Bottom", "Left"].forEach(side => { back.style[`border${side}Width`] = cs[`border${side}Width`]; });
    back.style.overflowY = t.scrollHeight > t.clientHeight + 1 ? "scroll" : "hidden";
    back.scrollTop = t.scrollTop;
    back.scrollLeft = t.scrollLeft;
  };
  // The passages' places in the layer: ranges of its one text (CSS highlights), or its <mark> where the API is missing
  let spans = [];
  const said = () => {
    if (!nav) return;
    const n = spans.length;
    nav.hidden = !n;
    nav.querySelector("[data-hl-count]").textContent = n ? T.hl.count(Math.max(0, current) + 1, n) : "";
  };
  const draw = () => {
    const text = t.value, found = passageRanges(text, list);
    // A text ending with a line break: the text area shows an empty last line, which a layer shows only when told
    const end = text.endsWith("\n") ? "\n" : "";
    if (window.CSS?.highlights && window.Highlight) {
      back.textContent = text + end;
      const node = back.firstChild;
      spans = node ? found.map(([a, b]) => { const r = new Range(); r.setStart(node, a); r.setEnd(node, b); return r; }) : [];
      HL_RANGES.set(back, spans);
      hlRefresh();
    } else {
      let html = "", pos = 0;
      for (const [a, b] of found) { html += `${esc(text.slice(pos, a))}<mark>${esc(text.slice(a, b))}</mark>`; pos = b; }
      back.innerHTML = `${html}${esc(text.slice(pos))}${end}`;
      spans = [...back.querySelectorAll("mark")];
    }
    place();
    said();
  };
  const later = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(draw); };
  // A passage: brought into view in the text area (a few lines above it), the cursor at its start
  const go = i => {
    if (!spans.length) return;
    current = (i + spans.length) % spans.length;
    // Its top in the layer's own pixels: measured on the screen, then brought back from the page's zoom
    const box = back.getBoundingClientRect(), scale = box.height / (back.clientHeight || 1) || 1;
    const top = (spans[current].getBoundingClientRect().top - box.top) / scale + back.scrollTop;
    t.scrollTop = Math.max(0, top - 3 * (parseFloat(getComputedStyle(t).lineHeight) || 20));
    const start = passageRanges(t.value, list)[current]?.[0] ?? 0;
    t.focus({ preventScroll: true });
    t.setSelectionRange(start, start);
    place();
    said();
  };
  t.addEventListener("input", later);
  t.addEventListener("scroll", () => { back.scrollTop = t.scrollTop; back.scrollLeft = t.scrollLeft; });
  new ResizeObserver(later).observe(t);
  window.addEventListener("resize", later);
  if (nav) {
    nav.querySelector("[data-hl-prev]").onclick = () => go(current - 1);
    nav.querySelector("[data-hl-next]").onclick = () => go(current + 1);
  }
  draw();
  return { go, draw, set: p => { list = p; current = -1; draw(); } };
}
export const hlNav = () => `<span class="hl-nav" hidden><button type="button" class="small-button" data-hl-prev title="${esc(T.hl.prev)}">◀</button>
  <span class="small muted" data-hl-count></span><button type="button" class="small-button" data-hl-next title="${esc(T.hl.next)}">▶</button></span>`;
