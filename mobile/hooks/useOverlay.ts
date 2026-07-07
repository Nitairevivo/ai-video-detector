import { useEffect, useCallback, useRef, useState } from "react";
import { NativeModules, Platform, AppState } from "react-native";

const { OverlayModule } = NativeModules;

export function useOverlay() {
  const [overlayActive, setOverlayActive] = useState(false);
  // True only while the user has explicitly asked to enable the overlay and we
  // are waiting for them to grant the permission in Settings. Gates the
  // AppState listener so the service is NEVER auto-started on a plain launch —
  // auto-starting a foreground service at startup crashes on Android 14+.
  const pendingStart = useRef(false);

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

  // Explicit user action only (the home-screen toggle). `silent` is kept for
  // API compatibility but no longer triggers any launch-time behaviour.
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
    } catch (e) {
      console.warn("Overlay stop failed:", e);
    }
  }, []);

  // Only finish a start the user already asked for, once they return from the
  // permission screen. Does nothing on a normal launch (pendingStart=false).
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active" || overlayActive || !pendingStart.current) return;
      if (!OverlayModule) return;
      try {
        const hasPerm = await OverlayModule.hasPermission();
        if (hasPerm) await actuallyStart();
      } catch {}
    });
    return () => sub.remove();
  }, [overlayActive, actuallyStart]);

  return { overlayActive, startOverlay, stopOverlay };
}
