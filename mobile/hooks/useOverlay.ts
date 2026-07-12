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
    try {
      const hasPerm = await OverlayModule.hasPermission();
      if (!hasPerm) {
        // Remember the intent, send the user to grant the permission, and
        // finish the start when they come back (see the AppState listener).
        pendingStart.current = true;
        await OverlayModule.requestPermission();
        return;
      }
      await actuallyStart();
    } catch (e) {
      console.warn("Overlay permission check failed:", e);
    }
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
  // that start. Does nothing on a normal launch (pendingStart=false).
  useEffect(() => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    refreshStatus();
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      if (pendingStart.current) {
        try {
          const hasPerm = await OverlayModule.hasPermission();
          if (hasPerm) {
            await actuallyStart();
            return;
          }
        } catch {}
      }
      refreshStatus();
    });
    return () => sub.remove();
  }, [actuallyStart, refreshStatus]);

  return { overlayActive, status, startOverlay, stopOverlay, refreshStatus };
}
