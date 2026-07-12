// Over-the-air (OTA) live updates via expo-updates + EAS Update.
//
// The app checks for a new published update shortly AFTER startup, downloads it
// in the background, and applies it on the next cold start. Hardened so it can
// never participate in a launch crash:
//   • expo-updates is imported LAZILY (dynamic import) inside a try/catch, so a
//     missing/misbehaving native module can't throw at module-load time (before
//     React mounts, where a React error boundary can't catch it — the classic
//     "opens then white-screen then closes" failure).
//   • every call is fully guarded and never throws.

export type OtaResult = "none" | "fetched" | "disabled" | "error";

// Resolve the expo-updates module without a top-level import. Returns null if it
// isn't available for any reason.
async function _loadUpdates(): Promise<any | null> {
  try {
    const mod = await import("expo-updates");
    return (mod as any)?.default ?? mod ?? null;
  } catch {
    return null;
  }
}

/**
 * Check for and download a newer OTA update. Returns "fetched" if a new bundle
 * was downloaded (it will apply on the next launch). Never throws.
 */
export async function checkForOta(): Promise<OtaResult> {
  try {
    if (typeof __DEV__ !== "undefined" && __DEV__) return "disabled";
    const Updates = await _loadUpdates();
    if (!Updates || !Updates.isEnabled) return "disabled";
    const res = await Updates.checkForUpdateAsync();
    if (res?.isAvailable) {
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
    if (typeof __DEV__ !== "undefined" && __DEV__) return;
    const Updates = await _loadUpdates();
    if (!Updates || !Updates.isEnabled) return;
    const res = await Updates.checkForUpdateAsync();
    if (res?.isAvailable) {
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync();
    }
  } catch {
    /* best-effort */
  }
}
