// @ts-check
/* vault-watch: which translated passage goes beside which passage of the source. For each mirror page the server keeps
   two lists (graph.mirror): the passages that changed in the source page, [old, new], and the edits the translator made
   in the mirror page, [current, proposed, (the translator's, once retouched)]. They are not pairs: a passage the
   translator left alone (the mirror already said it, or its edit could not be placed) has no edit, and paired by their
   rank every row after it would show a source beside the translation of another passage. Here each edit goes beside
   the passage it translates, judged by what a translation keeps (numbers, links, code, names, the kind of change and
   its length), in their order; a passage without one gets an empty cell, an edit without one its own row.
   Pure functions, no page: translation.js and publish.js draw the rows; tests/test_pairs.py runs them with node. */

// What a translation keeps of a text: links, code, numbers, words with a capital or a digit (names, versions), notes
const KEPT = /https?:\/\/[^\s)>\]]+|`[^`\n]+`|\[\^[^\]]+\]|\d+(?:[.,]\d+)*|[\p{L}\p{N}]*\p{Lu}[\p{L}\p{N}]*|[\p{L}]*\p{N}[\p{L}\p{N}]*/gu;
/** @param {string} text */
const kept = text => new Set((String(text || "").match(KEPT) || []).map(x => x.replace(/(\d),(\d)/g, "$1.$2").toLowerCase()));

/** @param {Set<string>} a @param {Set<string>} b */
function overlap(a, b) {
  if (!a.size || !b.size) return 0;
  let both = 0;
  a.forEach(x => { if (b.has(x)) both++; });
  return both / (a.size + b.size - both);
}

/** What a change does, and the text it brings: a passage removed, added, added to (after or before the text kept),
 *  or changed. @param {string} before @param {string} after */
function changeOf(before, after) {
  before = String(before || ""); after = String(after || "");
  if (!after.trim()) return { kind: "removed", text: before };
  if (!before.trim()) return { kind: "added", text: after };
  if (after.startsWith(before)) return { kind: "added", text: after.slice(before.length) };
  if (after.endsWith(before)) return { kind: "added", text: after.slice(0, after.length - before.length) };
  return { kind: "changed", text: after };
}

/** How likely `target` ([current, proposed]) translates `source` ([old, new]): above 0 they may go together, the
 *  higher the likelier. A removal goes with a removal only. @param {string[]} source @param {string[]} target */
export function likeness(source, target) {
  const s = changeOf(source[0], source[1]), t = changeOf(target[0], target[1]);
  if ((s.kind === "removed") !== (t.kind === "removed")) return -1;
  const ls = s.text.trim().length, lt = t.text.trim().length;
  return 1 + (s.kind === t.kind ? 0.3 : 0)
    + 2 * overlap(kept(s.text), kept(t.text))
    + overlap(kept(source[1] || source[0]), kept(target[1] || target[0]))
    + 0.5 * (ls && lt ? Math.min(ls, lt) / Math.max(ls, lt) : 0);
}

/** The rows of a mirror page, in the order of the page: {source, target, t}, `t` the rank of the edit in `target`
 *  (the key of its retouch, "<mirror page>#<t>"), -1 when the row has none; `source` or `target` null for the side
 *  that has nothing. The most likely pairing that keeps both orders (two passages never cross).
 *  @param {string[][]} sources @param {string[][]} targets
 *  @returns {{source: string[] | null, target: string[] | null, t: number}[]} */
export function alignPairs(sources, targets) {
  sources = sources || []; targets = targets || [];
  const n = sources.length, m = targets.length;
  const like = sources.map(s => targets.map(t => likeness(s, t)));
  // best[i][j]: the best total over the first i passages and the first j edits
  const best = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) for (let j = 1; j <= m; j++)
    best[i][j] = Math.max(best[i - 1][j], best[i][j - 1], like[i - 1][j - 1] > 0 ? best[i - 1][j - 1] + like[i - 1][j - 1] : -Infinity);
  const rows = [];
  let i = n, j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && like[i - 1][j - 1] > 0 && best[i][j] === best[i - 1][j - 1] + like[i - 1][j - 1]) {
      rows.push({ source: sources[i - 1], target: targets[j - 1], t: j - 1 }); i--; j--;
    } else if (i > 0 && (j === 0 || best[i][j] === best[i - 1][j])) {
      rows.push({ source: sources[i - 1], target: null, t: -1 }); i--;
    } else {
      rows.push({ source: null, target: targets[j - 1], t: j - 1 }); j--;
    }
  }
  return rows.reverse();
}
