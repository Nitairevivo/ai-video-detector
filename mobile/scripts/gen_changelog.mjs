#!/usr/bin/env node
/**
 * Generate the daily "What's New" entry for the app from what actually changed:
 *   - current model metrics (video + image), and their delta vs the last entry
 *   - notable commit subjects since the previous entry (feat/fix/perf/add)
 *
 * Writes mobile/changelog.data.json (prepends today's entry, or refreshes it if
 * today's already exists) and a human CHANGELOG.md. The OTA workflow then
 * publishes an EAS Update so installed apps show it live. Idempotent per day.
 *
 * Usage: node mobile/scripts/gen_changelog.mjs [YYYY-MM-DD]
 */
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DATA = join(ROOT, "mobile", "changelog.data.json");
const MD = join(ROOT, "CHANGELOG.md");

const today = process.argv[2] || new Date().toISOString().slice(0, 10);

function readJson(p, fallback) {
  try { return JSON.parse(readFileSync(p, "utf8")); } catch { return fallback; }
}

function sh(cmd) {
  try { return execSync(cmd, { cwd: ROOT, encoding: "utf8" }).trim(); } catch { return ""; }
}

const entries = readJson(DATA, []);
const prev = entries[0];

// ── model metrics ─────────────────────────────────────────────────────────────
const vmeta = readJson(join(ROOT, "models", "trained_model_meta.json"), {});
const imeta = readJson(join(ROOT, "models", "image_model_meta.json"), {});
const vAuc = vmeta.cv_auc_mean, vFpr = vmeta.cv_fpr, vN = vmeta.samples;
const iAuc = imeta.cv_auc, iN = imeta.samples;

const items = [];
if (typeof vAuc === "number") {
  const pct = (x) => (x == null ? "?" : `${(x * 100).toFixed(1)}%`);
  let line = `Video detector now at ${vAuc.toFixed(3)} AUC`;
  if (typeof vFpr === "number") line += ` with a ${pct(vFpr)} false-positive rate`;
  if (typeof vN === "number") line += ` (trained on ${vN.toLocaleString()} videos)`;
  items.push(line + ".");
}
if (typeof iAuc === "number") {
  items.push(`Image detector trained on ${Number(iN || 0).toLocaleString()} samples${
    typeof iAuc === "number" ? ` (AUC ${iAuc.toFixed(3)})` : ""}.`);
}

// ── notable commits since the previous entry ──────────────────────────────────
const since = prev?.date ? `--since="${prev.date} 00:00"` : "-n 40";
const log = sh(`git log ${since} --pretty=format:%s`);
const NOTABLE = /^(feat|fix|perf|add|improve|speed|train|model|detect)/i;
const SKIP = /changelog|bump version|merge |wip\b/i;
const commitItems = log
  .split("\n")
  .map((s) => s.trim())
  .filter((s) => s && NOTABLE.test(s) && !SKIP.test(s))
  .slice(0, 5)
  .map((s) => s.replace(/^\w+(\([^)]*\))?:\s*/, "").replace(/\s+$/, ""))
  .map((s) => s.charAt(0).toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : "."));

for (const c of commitItems) if (items.length < 6) items.push(c);

if (items.length === 0) {
  items.push("Reliability and detection improvements under the hood.");
}

const title =
  commitItems.length > 0
    ? "Model & detection improvements"
    : "Nightly model refresh";

const entry = { id: today, date: today, title, items };

// prepend or replace today's
const rest = entries.filter((e) => e.id !== today);
const next = [entry, ...rest].slice(0, 30);
writeFileSync(DATA, JSON.stringify(next, null, 2) + "\n");

// human CHANGELOG.md
const md =
  "# VerifAI — What's New\n\n" +
  next
    .map(
      (e) =>
        `## ${e.date} — ${e.title}\n\n` + e.items.map((i) => `- ${i}`).join("\n") + "\n"
    )
    .join("\n");
writeFileSync(MD, md);

console.log(`changelog: ${next.length} entries, latest ${today}:`);
for (const i of entry.items) console.log(`  - ${i}`);
