import { useEffect, useCallback, useRef, useState } from "react";
import { NativeModules, Platform, AppState } from "react-native";

const { OverlayModule } = NativeModules;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useOverlay() {
  const [overlayActive, setOverlayActive] = useState(false);
  // null = not checked yet, true/false = known. Lets the UI show the real state
  // ("granted" vs "grant permission") instead of always saying "fix".
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  // The user tapped enable and we sent them to Settings — finish the start when
  // they come back. Never auto-starts a service on a plain launch (that crashes
  // on Android 14+).
  const pendingStart = useRef(false);

  // Read the live permission state. Android reflects a freshly granted overlay
  // permission with a short delay, so poll a few times before trusting a false.
  const checkPermission = useCallback(async (retries = 1): Promise<boolean> => {
    if (Platform.OS !== "android" || !OverlayModule?.hasPermission) {
      setHasPermission(false);
      return false;
    }
    for (let i = 0; i < retries; i++) {
      try {
        const ok = await OverlayModule.hasPermission();
        if (ok) { setHasPermission(true); return true; }
      } catch { /* ignore, retry */ }
      if (i < retries - 1) await sleep(600);
    }
    setHasPermission(false);
    return false;
  }, []);

  const actuallyStart = useCallback(async () => {
    try {
      await OverlayModule.start();
      setOverlayActive(true);
      pendingStart.current = false;
      return true;
    } catch (e) {
      console.warn("Overlay start failed:", e);
      return false;
    }
  }, []);

  const startOverlay = useCallback(async () => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    // If the permission is already granted, just start — never bounce the user
    // to Settings again.
    if (await checkPermission(1)) {
      await actuallyStart();
      return;
    }
    // Otherwise remember the intent and open the grant screen; the AppState
    // listener finishes the start when they return.
    pendingStart.current = true;
    try { await OverlayModule.requestPermission(); } catch (e) { console.warn(e); }
  }, [checkPermission, actuallyStart]);

  const stopOverlay = useCallback(async () => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    pendingStart.current = false;
    try {
      await OverlayModule.stop();
      setOverlayActive(false);
    } catch (e) {
      console.warn("Overlay stop failed:", e);
    }
  }, []);

  // Check on mount, and again every time the app returns to the foreground — so
  // a permission granted in Settings is picked up automatically, and a start
  // the user already asked for is completed without another tap.
  useEffect(() => {
    if (Platform.OS !== "android") { setHasPermission(false); return; }
    checkPermission(1);
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      // Poll a few times — the grant may not be visible on the first check.
      const granted = await checkPermission(4);
      if (granted && pendingStart.current && !overlayActive) {
        await actuallyStart();
      }
    });
    return () => sub.remove();
  }, [checkPermission, actuallyStart, overlayActive]);

  return { overlayActive, hasPermission, startOverlay, stopOverlay, checkPermission };
}
