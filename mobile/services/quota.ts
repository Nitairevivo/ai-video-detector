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
