// VerifAI billing — real purchase + entitlement flow.
//
// This is a sideloaded APK (not on Google Play), so payment goes through a
// Stripe Checkout page opened in the browser — the correct, policy-compliant
// path for out-of-store Android apps. The server already exposes /register,
// /upgrade and /me; this module ties them to on-device state and pushes the
// Pro flag into the native floating button so its free daily limit lifts.
import * as SecureStore from "expo-secure-store";
import { Linking, NativeModules } from "react-native";

const API = "https://ai-video-detector-production-a305.up.railway.app";
const { OverlayModule } = NativeModules;

const K_EMAIL = "verifai_email";
const K_APIKEY = "verifai_apikey";
const K_PRO = "verifai_pro";

export type Tier = "free" | "pro" | "business" | "enterprise" | "ultra";

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((email || "").trim());
}

export async function getStoredEmail(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(K_EMAIL); } catch { return null; }
}

export async function isProCached(): Promise<boolean> {
  try { return (await SecureStore.getItemAsync(K_PRO)) === "1"; } catch { return false; }
}

async function setPro(isPro: boolean) {
  try { await SecureStore.setItemAsync(K_PRO, isPro ? "1" : "0"); } catch {}
  // Native floating button reads this to decide whether to enforce the limit.
  try { await OverlayModule?.setProStatus?.(isPro); } catch {}
}

/** Ensure this device has an account + API key for `email`. Returns the key,
 *  or null if the email already had a key on another device (the secret is
 *  only shown once, at first registration). */
async function ensureAccount(email: string): Promise<string | null> {
  const existing = await SecureStore.getItemAsync(K_APIKEY).catch(() => null);
  const savedEmail = await SecureStore.getItemAsync(K_EMAIL).catch(() => null);
  if (existing && savedEmail === email) return existing;

  const r = await fetch(`${API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const data = await r.json().catch(() => ({}));
  if (data?.api_key) {
    try {
      await SecureStore.setItemAsync(K_APIKEY, data.api_key);
      await SecureStore.setItemAsync(K_EMAIL, email);
    } catch {}
    return data.api_key as string;
  }
  // Email already registered elsewhere — no key is returned for this device.
  // Store the email so the email-keyed entitlement check works, but DROP any
  // stale key from a different account (it would report the wrong tier).
  try {
    await SecureStore.setItemAsync(K_EMAIL, email);
    if (savedEmail !== email) await SecureStore.deleteItemAsync(K_APIKEY);
  } catch {}
  return savedEmail === email ? existing : null;
}

/** Start a real Pro purchase: guarantee an account, then open Stripe Checkout.
 *  Throws with a readable message if the server/Stripe isn't configured yet. */
export async function startProCheckout(email: string): Promise<void> {
  const clean = email.trim();
  if (!isValidEmail(clean)) throw new Error("כתובת אימייל לא תקינה");
  await ensureAccount(clean);

  const r = await fetch(`${API}/upgrade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: clean, tier: "pro" }),
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    if (r.status === 400 && txt.includes("price")) {
      throw new Error("התשלום עדיין לא מחובר (חסר מפתח Stripe). ראה הוראות הגדרה.");
    }
    throw new Error("לא ניתן לפתוח את מסך התשלום כרגע. נסה שוב עוד רגע.");
  }
  const data = await r.json().catch(() => ({}));
  if (!data?.checkout_url) throw new Error("לא התקבל קישור תשלום מהשרת.");
  await Linking.openURL(data.checkout_url);
}

/** Re-check entitlement against the server and sync it to storage + native.
 *  Call on app resume and after returning from checkout. Returns true if Pro.
 *  Fails safe: on any network error it leaves the cached state untouched. */
export async function syncEntitlement(): Promise<boolean> {
  try {
    const key = await SecureStore.getItemAsync(K_APIKEY).catch(() => null);
    if (key) {
      const r = await fetch(`${API}/me`, { headers: { "X-Api-Key": key } });
      if (r.ok) {
        const data = await r.json().catch(() => ({}));
        const pro = ((data?.tier as Tier) || "free") !== "free";
        await setPro(pro);
        return pro;
      }
    }
    // No usable API key (fresh reinstall, or the sub was paid on another
    // device) — fall back to an email-keyed check so the user still unlocks.
    const email = await SecureStore.getItemAsync(K_EMAIL).catch(() => null);
    if (email) {
      const r2 = await fetch(`${API}/entitlement`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (r2.ok) {
        const d2 = await r2.json().catch(() => ({}));
        const pro = !!d2?.is_pro;
        await setPro(pro);
        return pro;
      }
    }
    return isProCached();
  } catch {
    return isProCached();
  }
}

/** Push the current cached Pro flag into the native button (e.g. on startup,
 *  so a reinstalled service picks it up before the first entitlement sync). */
export async function pushCachedProToNative(): Promise<void> {
  await setPro(await isProCached());
}
