import { useEffect, useCallback, useState } from "react";
import { NativeModules, Platform, AppState } from "react-native";

const { OverlayModule } = NativeModules;

export function useOverlay() {
  const [overlayActive, setOverlayActive] = useState(false);

  // Start the overlay service. When silent=true, never open the system
  // permission screen — used for auto-start so the app doesn't kick the
  // user into settings on every launch.
  const startOverlay = useCallback(async (silent = false) => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    try {
      const hasPerm = await OverlayModule.hasPermission();
      if (!hasPerm) {
        if (!silent) await OverlayModule.requestPermission();
        // User goes to settings — we'll check when they return
        return;
      }
      await OverlayModule.start();
      setOverlayActive(true);
    } catch (e) {
      console.warn("Overlay start failed:", e);
    }
  }, []);

  const stopOverlay = useCallback(async () => {
    if (Platform.OS !== "android" || !OverlayModule) return;
    try {
      await OverlayModule.stop();
      setOverlayActive(false);
    } catch (e) {
      console.warn("Overlay stop failed:", e);
    }
  }, []);

  // When user returns from the system permission screen, try again
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active" || overlayActive) return;
      if (!OverlayModule) return;
      try {
        const hasPerm = await OverlayModule.hasPermission();
        if (hasPerm) {
          await OverlayModule.start();
          setOverlayActive(true);
        }
      } catch {}
    });
    return () => sub.remove();
  }, [overlayActive]);

  return { overlayActive, startOverlay, stopOverlay };
}
