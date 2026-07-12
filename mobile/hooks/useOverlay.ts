import { useEffect, useCallback, useRef, useState } from "react";
import { NativeModules, Platform, AppState } from "react-native";

const { OverlayModule } = NativeModules;

export type OverlayStatus = {
  overlayPermission: boolean;
  accessibilityEnabled: boolean;
  serviceRunning: boolean;
};

const EMPTY_STATUS: OverlayStatus = {
  overlayPermission: false,
  accessibilityEnabled: false,
  serviceRunning: false,
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useOverlay() {
  const [overlayActive, setOverlayActive] = useState(false);
  const [status, setStatus] = useState<OverlayStatus>(EMPTY_STATUS);
  // True only while the user has explicitly asked to enable the overlay and we
  // are waiting for them to grant the permission in Settings. Gates the
  // AppState listener so the service is NEVER auto-started on a plain launch —
  // auto-starting a foreground service at startup crashes on Android 14+.
  const pendingStart = useRef(false);

  const refreshStatus = useCallback(async () => {
    if (Platform.OS !== "android" || !OverlayModule?.getStatus) return;
    try {
      const s: OverlayStatus = await OverlayModule.getStatus();
      setStatus(s);
      // The switch must reflect reality — the service can outlive the JS state
      // (app restarted) or die under it (system killed it).
      setOverlayActive(s.serviceRunning);
    } catch {}
  }, []);

  // Read the live permission state. Android reflects a freshly granted overlay
  // permission with a short delay, so poll a few times before trusting a false.
  const checkPermission = useCallback(async (retries = 1): Promise<boolean> => {
    if (Platform.OS !== "android" || !OverlayModule?.hasPermission) return false;
    for (let i = 0; i < retries; i++) {
      try {
        const ok = await OverlayModule.hasPermission();
        if (ok) return true;
      } catch { /* ignore, retry */ }
      if (i < retries - 1) await sleep(600);
    }
    return false;
  }, []);

  const actuallyStart = useCallback(async () => {
    try {
      await OverlayModule.start();
      setOverlayActive(true);
      pendingStart.current = false;
      refreshStatus();
      return true;
    } catch (e) {
      console.warn("Overlay start failed:", e);
      return false;
    }
  }, [refreshStatus]);

  // Explicit user action only (the home-screen toggle) — never called at launch.
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
      refreshStatus();
    } catch (e) {
      console.warn("Overlay stop failed:", e);
    }
  }, [refreshStatus]);

  // On mount: read the real state (service may already be running from a
  // previous session). On every return to foreground: re-read permissions and,
  // if the user just granted the overlay permission they asked for, finish
  // that start (polling a few times — the grant may not be visible on the
  // first check). Does nothing on a normal launch (pendingStart=false).
  useEffect(() => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    refreshStatus();
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      if (pendingStart.current) {
        const granted = await checkPermission(4);
        if (granted) {
          await actuallyStart();
          return;
        }
      }
      refreshStatus();
    });
    return () => sub.remove();
  }, [checkPermission, actuallyStart, refreshStatus]);

  return { overlayActive, status, startOverlay, stopOverlay, refreshStatus, checkPermission };
}
