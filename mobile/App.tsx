import React, { useState, useEffect } from "react";
import {
  View, Text, ScrollView, TouchableOpacity, Platform, NativeModules,
} from "react-native";
import { StatusBar } from "expo-status-bar";

// Global JS error handler — set up before anything else runs
let _jsError: string | null = null;
let _setJsError: ((e: string) => void) | null = null;
(function () {
  try {
    const EU = (global as any).ErrorUtils;
    if (!EU) return;
    EU.setGlobalHandler?.((error: Error | string, _isFatal: boolean) => {
      const msg = (typeof error === "string"
        ? error
        : (error?.stack || error?.message || String(error))
      ).slice(0, 3000);
      _jsError = msg;
      if (_setJsError) _setJsError(msg);
      // Don't call original handler — keep error on screen for screenshot
    });
  } catch {}
})();

export default function App() {
  const [jsError, setJsError] = useState<string | null>(_jsError);
  const [lines, setLines] = useState<string[]>([]);
  const [overlayLog, setOverlayLog] = useState<string>("");

  const log = (msg: string) =>
    setLines((p) => [...p, new Date().toISOString().slice(11, 19) + " " + msg]);

  useEffect(() => {
    _setJsError = setJsError;
    if (_jsError) setJsError(_jsError);
    return () => { _setJsError = null; };
  }, []);

  useEffect(() => {
    log(`Platform: ${Platform.OS} ${Platform.Version}`);
    log(`OverlayModule: ${NativeModules.OverlayModule ? "LOADED ✓" : "NULL ✗"}`);
    log(`DiagModule: ${NativeModules.DiagModule ? "LOADED ✓" : "NULL ✗"}`);
    log(`Modules: ${Object.keys(NativeModules).slice(0, 10).join(", ")}`);

    // DiagModule always loads even if OverlayModule crashes
    try {
      const dm = NativeModules.DiagModule;
      if (dm) {
        const dp = dm.getError?.();
        if (dp) {
          dp.then((err: string | null) => {
            log("Diag: " + (err || "all_ok"));
          }).catch((e: any) => log("DiagModule err: " + (e?.message || e)));
        }
      } else {
        // Fallback: try OverlayModule directly
        const p = NativeModules.OverlayModule?.getLastCrash?.();
        if (p) {
          p.then((crash: string | null) => {
            log(crash ? "⚠ Prev crash: " + crash.slice(0, 300) : "No prev crash");
          }).catch((e: any) => log("getLastCrash err: " + (e?.message || e)));
        } else {
          log("No diag available");
        }
      }
    } catch (e: any) {
      log("Diag threw: " + (e?.message || String(e)));
    }
  }, []);

  async function testOverlay() {
    const OM = NativeModules.OverlayModule;
    if (!OM) {
      setOverlayLog("❌ OverlayModule is NULL — module not registered");
      return;
    }
    try {
      setOverlayLog("Checking permission...");
      const hasPerm = await OM.hasPermission();
      setOverlayLog("hasPermission: " + hasPerm);
      if (!hasPerm) {
        setOverlayLog("Opening permission screen...");
        await OM.requestPermission();
        setOverlayLog("Permission dialog opened — grant then come back");
        return;
      }
      setOverlayLog("Starting overlay service...");
      const r = await OM.start();
      setOverlayLog("✓ Started! result: " + JSON.stringify(r));
    } catch (e: any) {
      setOverlayLog("❌ Error: " + (e?.message || String(e)));
    }
  }

  // JS error screen — stays open until dismissed
  if (jsError) {
    return (
      <View style={{ flex: 1, backgroundColor: "#1a0000", padding: 20, justifyContent: "center" }}>
        <Text style={{ color: "#f97316", fontSize: 16, fontWeight: "800", marginBottom: 8 }}>
          JS ERROR — צלם ושלח!
        </Text>
        <ScrollView style={{ maxHeight: 360, marginBottom: 16 }}>
          <Text style={{ color: "#fca5a5", fontSize: 9, fontFamily: "monospace" }} selectable>
            {jsError}
          </Text>
        </ScrollView>
        <TouchableOpacity
          onPress={() => setJsError(null)}
          style={{ backgroundColor: "#4b5563", padding: 12, borderRadius: 8 }}
        >
          <Text style={{ color: "white", textAlign: "center" }}>המשך בכל זאת</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#06060f", padding: 16 }}>
      <StatusBar style="light" />

      <Text style={{ color: "#a78bfa", fontSize: 24, fontWeight: "800", marginTop: 44, marginBottom: 2 }}>
        VerifAI v9
      </Text>
      <Text style={{ color: "#374151", fontSize: 11, marginBottom: 20 }}>
        diagnostic — אם רואה את זה: צלם מסך ושלח!
      </Text>

      <ScrollView
        style={{ flex: 1, backgroundColor: "#0a0a16", borderRadius: 8, padding: 10, marginBottom: 12 }}
      >
        {lines.map((l, i) => (
          <Text key={i} style={{ color: "#6ee7b7", fontSize: 10, fontFamily: "monospace", marginBottom: 2 }}>
            {l}
          </Text>
        ))}
        {lines.length === 0 && (
          <Text style={{ color: "#1f2937", fontSize: 10 }}>loading...</Text>
        )}
      </ScrollView>

      {overlayLog ? (
        <Text style={{ color: "#fbbf24", fontSize: 10, textAlign: "center", marginBottom: 10 }}>
          {overlayLog}
        </Text>
      ) : null}

      <TouchableOpacity
        onPress={testOverlay}
        style={{ backgroundColor: "#4f46e5", padding: 14, borderRadius: 12 }}
      >
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>
          Test Overlay (manual)
        </Text>
      </TouchableOpacity>
    </View>
  );
}
