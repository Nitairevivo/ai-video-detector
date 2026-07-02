import React, { useState, useEffect } from "react";
import { View, Text, ScrollView, NativeModules } from "react-native";
import { StatusBar } from "expo-status-bar";

export default function App() {
  const [lines, setLines] = useState<string[]>([]);

  const log = (msg: string) =>
    setLines((p) => [...p, new Date().toISOString().slice(11, 19) + " " + msg]);

  useEffect(() => {
    log("VerifAI v11 started ✓");
    const moduleKeys = Object.keys(NativeModules);
    log(`Total modules: ${moduleKeys.length}`);
    log(`DiagModule: ${NativeModules.DiagModule ? "LOADED ✓" : "NULL ✗"}`);
    log(`Modules: ${moduleKeys.slice(0, 12).join(", ")}`);

    const dm = NativeModules.DiagModule;
    if (dm?.getError) {
      dm.getError()
        .then((r: string | null) => log("getError: " + (r || "null")))
        .catch((e: any) => log("getError err: " + (e?.message || e)));
    } else {
      log("DiagModule.getError not available");
    }
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: "#06060f", padding: 16 }}>
      <StatusBar style="light" />
      <Text style={{ color: "#a78bfa", fontSize: 22, fontWeight: "800", marginTop: 44, marginBottom: 4 }}>
        VerifAI v11
      </Text>
      <Text style={{ color: "#374151", fontSize: 11, marginBottom: 16 }}>
        nuclear test — אם רואה את זה: שלח צילום מסך!
      </Text>
      <ScrollView style={{ flex: 1, backgroundColor: "#0a0a16", borderRadius: 8, padding: 10 }}>
        {lines.map((l, i) => (
          <Text key={i} style={{ color: "#6ee7b7", fontSize: 11, fontFamily: "monospace", marginBottom: 3 }}>
            {l}
          </Text>
        ))}
        {lines.length === 0 && (
          <Text style={{ color: "#374151", fontSize: 10 }}>initializing...</Text>
        )}
      </ScrollView>
    </View>
  );
}
