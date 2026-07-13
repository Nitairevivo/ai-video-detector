// ─── Freemium quota — consumer-facing scan limits ────────────────────────────
//
// The server already has an API-key billing system for the B2B API. This is the
// separate CONSUMER model that runs inside the app: a free monthly scan
// allowance, and Pro / Pro-Max tiers that lift it. State is stored locally
// (SecureStore) and is the source of truth for gating the UI. When real store
// billing is wired up, the purchase callback just calls `setTier()` — nothing
// else in the app has to change.
//
// NOTE: local counting is deliberately honest-but-not-Fort-Knox. A determined
// user could clear app data to reset the counter; that's fine for a €19 consumer
// product. Revenue protection that matters (auto-scan, deep analysis) is gated
// server-side by the paid tier, not by this counter.

import * as SecureStore from "expo-secure-store";

export type Tier = "free" | "pro" | "promax";

export const TIERS: Record<Tier, {
  monthlyScans: number;        // Infinity for paid
  autoScan: boolean;           // floating-button auto-detection
  deepAnalysis: boolean;       // full multi-layer report + frame timeline
  batch: boolean;              // check many at once
  priceIls: number;
}> = {
  free:   { monthlyScans: 10,       autoScan: false, deepAnalysis: false, batch: false, priceIls: 0 },
  pro:    { monthlyScans: Infinity, autoScan: true,  deepAnalysis: true,  batch: false, priceIls: 19 },
  promax: { monthlyScans: Infinity, autoScan: true,  deepAnalysis: true,  batch: true,  priceIls: 49 },
};

const TIER_KEY = "verifai_tier";
const USAGE_KEY = "verifai_usage"; // { period: "2026-07", count: 3 }

export type Usage = { period: string; count: number };

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export async function getTier(): Promise<Tier> {
  try {
    const t = await SecureStore.getItemAsync(TIER_KEY);
    if (t === "pro" || t === "promax") return t;
  } catch {}
  return "free";
}

export async function setTier(tier: Tier): Promise<void> {
  try { await SecureStore.setItemAsync(TIER_KEY, tier); } catch {}
}

// ─── Redeem codes ─────────────────────────────────────────────────────────────
// Offline, checksum-validated unlock codes. Used for (a) the owner unlocking
// Pro-Max permanently on his own devices, and (b) the manual "pay on Bit → get a
// code" flow. Codes look like  VF-MAX-7K3P-9QF . Validation is local — a code is
// a serial plus a checksum of (tier + serial + salt), so the app can verify any
// code without a server or a stored list. Not cryptographically strong (the salt
// ships in the bundle); good enough for a low-stakes consumer unlock, rotate the
// salt if codes ever leak widely.
const SALT = "VF-2026-mythos-x9";
const ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no ambiguous 0/O/1/I/L

function djb2(str: string): number {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = (((h << 5) + h) ^ str.charCodeAt(i)) >>> 0;
  return h;
}

function checksum(seed: string, len = 3): string {
  let n = djb2(seed);
  let out = "";
  for (let i = 0; i < len; i++) { out = ALPHABET[n % ALPHABET.length] + out; n = Math.floor(n / ALPHABET.length); }
  return out;
}

/** Validate a redeem code and return the tier it grants, or null if invalid. */
export function tierForCode(raw: string): Tier | null {
  const code = (raw || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const m = code.match(/^VF(PRO|MAX)([A-Z0-9]{4})([A-Z0-9]{3})$/);
  if (!m) return null;
  const [, seg, serial, check] = m;
  if (checksum(seg + serial + SALT) !== check) return null;
  return seg === "MAX" ? "promax" : "pro";
}

/** Redeem a code: on success persists the tier permanently and returns it. */
export async function redeemCode(raw: string): Promise<Tier | null> {
  const tier = tierForCode(raw);
  if (tier) await setTier(tier);
  return tier;
}

export async function getUsage(): Promise<Usage> {
  const period = currentPeriod();
  try {
    const raw = await SecureStore.getItemAsync(USAGE_KEY);
    if (raw) {
      const u = JSON.parse(raw) as Usage;
      // A new month resets the allowance.
      if (u.period === period) return u;
    }
  } catch {}
  return { period, count: 0 };
}

/** How many free scans are left this month (Infinity for paid tiers). */
export async function scansRemaining(): Promise<number> {
  const tier = await getTier();
  const limit = TIERS[tier].monthlyScans;
  if (limit === Infinity) return Infinity;
  const usage = await getUsage();
  return Math.max(0, limit - usage.count);
}

/** True when the user may run another scan right now. */
export async function canScan(): Promise<boolean> {
  return (await scansRemaining()) > 0;
}

/** Record one consumed scan. Paid tiers are unmetered. Returns updated usage. */
export async function recordScan(): Promise<Usage> {
  const tier = await getTier();
  const usage = await getUsage();
  if (TIERS[tier].monthlyScans === Infinity) return usage;
  const next: Usage = { period: usage.period, count: usage.count + 1 };
  try { await SecureStore.setItemAsync(USAGE_KEY, JSON.stringify(next)); } catch {}
  return next;
}
