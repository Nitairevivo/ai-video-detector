// Over-the-air (OTA) live updates via expo-updates + EAS Update.
//
// The app checks for a new published update on every launch, downloads it in the
// background, and applies it on the next cold start (expo-updates default). This
// module wraps that with a safe manual check so improvements land promptly and
// nothing ever crashes if the update server is unreachable or we're in Expo Go.

import * as Updates from "expo-updates";

export type OtaResult = "none" | "fetched" | "disabled" | "error";

/**
 * Check for and download a newer OTA update. Returns "fetched" if a new bundle
 * was downloaded (it will apply on the next launch). Never throws.
 */
export async function checkForOta(): Promise<OtaResult> {
  // No OTA in dev / Expo Go — Updates.isEnabled is false there.
  if (__DEV__ || !Updates.isEnabled) return "disabled";
  try {
    const res = await Updates.checkForUpdateAsync();
    if (res.isAvailable) {
      await Updates.fetchUpdateAsync();
      return "fetched";
    }
    return "none";
  } catch {
    return "error";
  }
}

/**
 * Fetch and immediately reload into the new update. Use only behind an explicit
 * user action ("Update now"); the silent path lets it apply on next launch.
 */
export async function applyOtaNow(): Promise<void> {
  try {
    if (__DEV__ || !Updates.isEnabled) return;
    const res = await Updates.checkForUpdateAsync();
    if (res.isAvailable) {
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync();
    }
  } catch {
    /* best-effort */
  }
}
