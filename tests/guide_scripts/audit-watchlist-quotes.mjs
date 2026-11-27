#!/usr/bin/env node
/**
 * audit-watchlist-quotes.mjs
 *
 * Lists the watchlist rows whose quoted claim is no longer in their page: the page
 * was corrected, trimmed or reworded and the row was not. Such a row sends the old
 * wording to every re-check of the due claims (2026-11-26: four claims reported as
 * outdated when their pages were already current) and no longer lets `grep` find
 * the sentence it tracks.
 *
 * A claim is the text between the first « and the last » of the Claim cell. It is
 * cut at every « … » (or "...") and at inner guillemets (« a » / « b » joins two
 * passages), and each fragment of 12 characters or more must be found in the page. Page and fragments are compared without emphasis, code marks,
 * links (their text is kept), footnote calls, blockquote marks, escaped pipes and
 * with every run of spaces as one.
 *
 * Usage:
 *   node scripts/audit-watchlist-quotes.mjs                 # Markdown report, exit 0
 *   node scripts/audit-watchlist-quotes.mjs --json=out.json # also a JSON report
 *   node scripts/audit-watchlist-quotes.mjs --strict        # exit 1 when a row drifts
 *   node scripts/audit-watchlist-quotes.mjs --write=in.json # rewrite the rows it names (vault-watch-agent)
 *
 * npm script: audit:watchlist-quotes (warn-only, not in `npm test`)
 */
import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { VAULT_ROOT } from "./lib/vault-walk.mjs";

const args = process.argv.slice(2);
const STRICT = args.includes("--strict");
const jsonArg = args.find((a) => a.startsWith("--json="));
const OUT_JSON = jsonArg ? jsonArg.slice("--json=".length) : null;
const writeArg = args.find((a) => a.startsWith("--write="));
const IN_WRITE = writeArg ? writeArg.slice("--write=".length) : null;

const WATCHLIST_DIR = ".agents/vault-maintenance/watchlist";
const MIN_FRAGMENT = 12;

/** Inline math as it reads: `\sim 273 \text{ Go/s}` → `~273 Go/s`, `0{,}5` → `0,5`, `\times` → `×`. */
function latex(math) {
  let out = math;
  for (let before = ""; before !== out; ) { // innermost first: `\mathbf{15,4 \text{ tokens/s}}`
    before = out;
    out = out.replace(/\\(?:text|mathbf|mathrm|textbf)\{([^{}]*)\}/g, "$1");
  }
  return out
    .replace(/\{,\}/g, ",")
    .replace(/\\sim\s*/g, "~")
    .replace(/\\approx/g, "≈")
    .replace(/\\times/g, "×")
    .replace(/\\cdot\s*/g, "·")
    .replace(/\\to\b/g, "→")
    .replace(/\^2\b/g, "²")
    .replace(/\\(?:[ ,;!]|quad)/g, " ")
    .replace(/[{}]/g, "");
}

/** Text as the comparison sees it: what a reader reads, spaces folded. */
function normalise(text) {
  return text
    .replace(/^\s*>\s?/gm, "") // blockquote and callout marks
    .replace(/[ \t]\\[ \t]*\r?\n/g, " ") // a shell command continued on the next line (`vllm serve x \`)
    .replace(/\\\|/g, "|") // escaped pipes in tables and watchlist cells
    .replace(/\[\^[^\]]+\]/g, "") // footnote calls
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // Markdown links and images: their text
    .replace(/\[\[(?:[^\]|]*\|)?([^\]]*)\]\]/g, "$1") // wikilinks: their alias or target
    .replace(/\\\$/g, "\u0001") // an escaped dollar is a dollar, not math
    // inline math (`$\sim 273 \text{ Go/s}$`, `$614$`): what it reads as; two prices ("4 $ … 20 $") are not math
    .replace(/\$(?=\S)([^$\n]*?)(?<=\S)\$/g, (all, m) => (/\\|\{|^[\d.,]+$/.test(m) ? latex(m) : all))
    .replace(/\u0001/g, "$")
    .replace(/[*`]/g, "") // emphasis and code marks
    .replace(/[   ]/g, " ") // non-breaking and thin spaces
    .replace(/[’ʼ]/g, "'") // typographic apostrophes
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The quoted passages of a Claim cell, or null when the cell quotes nothing: each « … » at the outer level, the
 * guillemets the page itself uses kept inside (« un « Trusted Hosts » ») and the cell's own words between two
 * passages left out (« a » / description « b »). A last « left open is ignored; no passage closed at all: from
 * the first « to the last ».
 */
function quoteOf(cell) {
  const passages = [];
  let depth = 0;
  let current = "";
  for (const ch of cell) {
    if (ch === "«") {
      if (depth > 0) current += ch;
      depth += 1;
    } else if (ch === "»" && depth > 0) {
      depth -= 1;
      if (depth > 0) current += ch;
      else {
        passages.push(current);
        current = "";
      }
    } else if (depth > 0) current += ch;
  }
  if (passages.length) return passages; // a last « left open is the cell's own comment
  const start = cell.indexOf("«");
  const end = cell.lastIndexOf("»");
  return start >= 0 && end > start ? [cell.slice(start + 1, end)] : null;
}

/** The fragments of the passages that must each be found in the page. */
function fragments(passages) {
  return passages
    .flatMap((p) => normalise(p).split(/…|\.\.\.|\(…\)/))
    .map((s) => s.replace(/^[\s«».,;:)(]+|[\s«».,;:(\\]+$/g, "")) // a quoted command's trailing `\` too
    .filter((s) => s.length >= MIN_FRAGMENT);
}

/** Split a watchlist table row into its cells, escaped pipes kept inside them. */
function cellsOf(line) {
  return line
    .replace(/\\\|/g, "\u0000")
    .split("|")
    .slice(1, -1)
    .map((c) => c.split("\u0000").join("\\|").trim());
}

/** A cell as written in the table: a literal pipe escaped, no line break. */
function asCell(text) {
  return String(text).replace(/\r?\n/g, " ").replace(/(?<!\\)\|/g, "\\|").trim();
}

/**
 * Rewrite the rows `updates` names: { updates: [{ file, line, claim, new_claim?, new_value?, note?, remove? }] }.
 * `claim` is the Claim cell as read (the row must still hold it); `new_claim` replaces it, `new_value` replaces
 * « Value in page », `note` is appended to Note; `remove` deletes the row (its sentence is gone). Checked, Status
 * and Recheck by are left as they are: they move only after a web check. Prints { written, removed, refused }.
 */
function writeUpdates(path) {
  const { updates = [] } = JSON.parse(readFileSync(path, "utf8"));
  const byFile = new Map();
  for (const u of updates) byFile.set(u.file, [...(byFile.get(u.file) ?? []), u]);
  const done = { written: 0, removed: 0, refused: [] };
  for (const [file, list] of byFile) {
    const abs = join(VAULT_ROOT, file);
    if (!file.startsWith(`${WATCHLIST_DIR}/`) || !existsSync(abs)) {
      done.refused.push(...list.map((u) => ({ file, line: u.line, why: "not a watchlist file" })));
      continue;
    }
    const raw = readFileSync(abs, "utf8");
    const eol = raw.includes("\r\n") ? "\r\n" : "\n";
    const lines = raw.split(/\r?\n/);
    for (const u of [...list].sort((a, b) => b.line - a.line)) {
      const cells = lines[u.line - 1]?.startsWith("| `") ? cellsOf(lines[u.line - 1]) : [];
      if (cells.length < 10 || cells[1] !== u.claim) {
        done.refused.push({ file, line: u.line, why: "the row no longer holds this claim" });
        continue;
      }
      if (u.remove) {
        lines.splice(u.line - 1, 1);
        done.removed += 1;
        continue;
      }
      if (u.new_claim) cells[1] = asCell(u.new_claim);
      if (u.new_value) cells[3] = asCell(u.new_value);
      if (u.note) cells[8] = cells[8] ? `${cells[8]} ; ${asCell(u.note)}` : asCell(u.note);
      lines[u.line - 1] = `| ${cells.join(" | ")} |`;
      done.written += 1;
    }
    writeFileSync(abs, lines.join(eol), "utf8");
  }
  console.log(JSON.stringify(done));
  process.exit(done.refused.length ? 1 : 0);
}

if (IN_WRITE) writeUpdates(IN_WRITE);

const pages = new Map();
function pageText(rel) {
  if (!pages.has(rel)) {
    const abs = join(VAULT_ROOT, rel);
    pages.set(rel, existsSync(abs) ? normalise(readFileSync(abs, "utf8")) : null);
  }
  return pages.get(rel);
}

const drifted = [];
let rows = 0;
let unquoted = 0;
const dir = join(VAULT_ROOT, WATCHLIST_DIR);
for (const file of readdirSync(dir).filter((f) => f.endsWith(".md")).sort()) {
  const lines = readFileSync(join(dir, file), "utf8").split(/\r?\n/);
  lines.forEach((line, i) => {
    if (!line.startsWith("| `")) return;
    const cells = cellsOf(line);
    if (cells.length < 10) return;
    const page = cells[0].replace(/`/g, "");
    if (!page.endsWith(".md")) return;
    rows += 1;
    const quote = quoteOf(cells[1]);
    if (quote === null) {
      unquoted += 1;
      return;
    }
    const base = { file: `${WATCHLIST_DIR}/${file}`, line: i + 1, page, claim: cells[1], value: cells[3],
      status: cells[7], recheck_by: cells[9] ?? "" };
    const text = pageText(page);
    if (text === null) {
      drifted.push({ ...base, reason: "page-missing", missing: [], found: 0, total: 0 });
      return;
    }
    const parts = fragments(quote);
    const missing = parts.filter((p) => !text.includes(p));
    if (missing.length) {
      drifted.push({ ...base, reason: missing.length === parts.length ? "quote-missing" : "fragment-missing",
        missing, found: parts.length - missing.length, total: parts.length });
    }
  });
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

const count = (r) => drifted.filter((d) => d.reason === r).length;
const due = drifted.filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d.recheck_by)).length;
const md = [
  "# Watchlist quotes",
  "",
  `${rows} rows, ${unquoted} without a « quote ». **${drifted.length}** quote no longer found in their page: ` +
    `${count("quote-missing")} entirely, ${count("fragment-missing")} in part, ${count("page-missing")} page missing; ` +
    `${due} of them carry a « Recheck by » date.`,
  "",
];
if (drifted.length) {
  md.push("| Row | Page | Recheck by | Not found |", "| :-- | :-- | :-- | :-- |");
  for (const d of drifted) {
    const what = d.reason === "page-missing" ? "(page missing)"
      : `${d.found}/${d.total} found; « ${d.missing[0].slice(0, 100).replace(/\|/g, "\\|")}${d.missing[0].length > 100 ? "…" : ""} »`;
    md.push(`| \`${d.file.split("/").pop()}:${d.line}\` | \`${d.page}\` | ${d.recheck_by} | ${what} |`);
  }
  md.push("");
}
md.push("_Generated by `scripts/audit-watchlist-quotes.mjs`. A row listed here quotes wording its page no longer has: " +
  "quote the page as it reads today (`.agents/vault-maintenance/freshness-watchlist.md`, « If the wording changes, update the row »), " +
  "or remove the row when its sentence is gone. Checked and Status move only after a web check._");
console.log(md.join("\n"));

if (OUT_JSON) {
  writeFileSync(OUT_JSON, JSON.stringify({ rows, unquoted, drifted }, null, 2) + "\n", "utf8");
}
process.exit(STRICT && drifted.length ? 1 : 0);
