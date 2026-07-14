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

  // Try to bring the button up and CONFIRM it actually came up by reading the
  // running service — the source of truth that survives OEMs whose
  // canDrawOverlays() lies. Returns true only if the overlay is really live.
  const actuallyStart = useCallback(async (): Promise<boolean> => {
    try {
      await OverlayModule.start();
      // The foreground service + addView happen just after; give it a moment,
      // then confirm via serviceRunning.
      for (let i = 0; i < 4; i++) {
        await sleep(400);
        try {
          const s: OverlayStatus = await OverlayModule.getStatus();
          if (s.serviceRunning) {
            setStatus(s);
            setOverlayActive(true);
            pendingStart.current = false;
            return true;
          }
        } catch {}
      }
      return false;
    } catch (e) {
      console.warn("Overlay start failed:", e);
      return false;
    }
  }, []);

  // Explicit user action only (the home-screen toggle) — never called at launch.
  // Returns true if the button actually came up. On false the caller shows the
  // OEM-permission help so the user isn't left with a switch that silently
  // refuses to turn on.
  const startOverlay = useCallback(async (): Promise<boolean> => {
    if (Platform.OS !== "android" || !OverlayModule) return false;
    // ALWAYS try to start first — don't trust canDrawOverlays, which lies on
    // many OEM skins. If the button actually comes up, we're done.
    if (await actuallyStart()) return true;
    // The overlay couldn't be added → open the standard grant screen and arm the
    // AppState listener to finish the start when they return. Also signal failure
    // so the caller can show device-specific guidance (Xiaomi & co. need an
    // extra hidden 'pop-up while in background' permission).
    pendingStart.current = true;
    try { await OverlayModule.requestPermission(); } catch (e) { console.warn(e); }
    return false;
  }, [actuallyStart]);

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
        // They just came back from the grant screen — try to bring the button
        // up and confirm it (actuallyStart trusts serviceRunning, not the flag).
        if (await actuallyStart()) return;
      }
      refreshStatus();
    });
    return () => sub.remove();
  }, [checkPermission, actuallyStart, refreshStatus]);

  return { overlayActive, status, startOverlay, stopOverlay, refreshStatus, checkPermission };
}
