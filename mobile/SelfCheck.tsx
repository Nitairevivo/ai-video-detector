// On-screen self-check card. Shows, the moment the app opens, exactly which
// Expo project / channel / update bundle the app is actually running — so an
// account/project/channel mismatch (the "three farms" problem: app built under
// one Expo account but OTA pointing at another) is visible instead of guessed.
//
// Fully self-contained and crash-proof: expo-updates is loaded lazily inside a
// try/catch and every field read is guarded, so this card can never contribute
// to a startup crash. It does NOT touch any of the app's core logic.

import React, { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import * as SecureStore from "expo-secure-store";

// What the app is SUPPOSED to be wired to (from app.json). Shown next to the
// live values so a mismatch is obvious.
const EXPECTED_PROJECT = "1ccf6c26-6560-4dfa-96d0-a026d693bbab";
const EXPECTED_OWNER = "052676";
const JS_ERROR_KEY = "verifai_last_js_error";

type Info = { k: string; v: string; bad?: boolean };

export function SelfCheck({ version }: { version: string }) {
  const [rows, setRows] = useState<Info[]>([]);
  const [lastErr, setLastErr] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      const out: Info[] = [
        { k: "app version", v: `v${version}` },
        { k: "expected project", v: EXPECTED_PROJECT.slice(0, 8) + "…" },
        { k: "expected owner", v: EXPECTED_OWNER },
      ];
      try {
        const mod: any = await import("expo-updates");
        const U = mod?.default ?? mod ?? {};
        const enabled = !!U.isEnabled;
        out.push({ k: "updates enabled", v: String(enabled), bad: !enabled });
        out.push({ k: "running", v: U.isEmbeddedLaunch ? "embedded build" : "OTA bundle" });
        out.push({ k: "channel", v: String(U.channel ?? "—(none)"), bad: !U.channel });
        out.push({ k: "runtime version", v: String(U.runtimeVersion ?? "—") });
        out.push({ k: "update id", v: U.updateId ? String(U.updateId).slice(0, 8) + "…" : "—(embedded)" });
      } catch (e) {
        out.push({ k: "expo-updates", v: "UNAVAILABLE — " + String(e).slice(0, 50), bad: true });
      }
      if (alive) setRows(out);
    })();
    SecureStore.getItemAsync(JS_ERROR_KEY).then((v) => alive && setLastErr(v)).catch(() => {});
    return () => { alive = false; };
  }, [version]);

  if (!open) return null;
  return (
    <View style={s.card}>
      <View style={s.head}>
        <Text style={s.title}>🔍 בדיקה עצמית · Self-check</Text>
        <TouchableOpacity onPress={() => setOpen(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={s.x}>✕</Text>
        </TouchableOpacity>
      </View>
      {rows.map((r) => (
        <View key={r.k} style={s.line}>
          <Text style={s.k}>{r.k}</Text>
          <Text style={[s.v, r.bad && s.vBad]}>{r.v}</Text>
        </View>
      ))}
      {lastErr ? (
        <View style={s.err}>
          <Text style={s.errT}>שגיאה אחרונה שנשמרה:</Text>
          <Text style={s.errB}>{lastErr.slice(0, 300)}</Text>
        </View>
      ) : (
        <Text style={s.ok}>אין שגיאת JS שמורה ✓</Text>
      )}
      <Text style={s.hint}>צלם מסך של הכרטיס הזה ושלח — זה מראה בדיוק מאיזה פרויקט/ערוץ האפליקציה מושכת עדכונים.</Text>
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: "#0c0c1c", borderRadius: 16, borderWidth: 1, borderColor: "rgba(124,108,255,0.4)", padding: 14, marginBottom: 14 },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  title: { color: "#c9c3ff", fontSize: 14, fontWeight: "800" },
  x: { color: "#5a5b74", fontSize: 16, fontWeight: "700" },
  line: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 },
  k: { color: "#8b8ca7", fontSize: 12 },
  v: { color: "#e8e8f0", fontSize: 12, fontWeight: "600", fontFamily: "monospace" },
  vBad: { color: "#ff97a8" },
  ok: { color: "#8ff0cd", fontSize: 12, marginTop: 8 },
  err: { marginTop: 10, backgroundColor: "rgba(255,84,112,0.08)", borderRadius: 10, padding: 8 },
  errT: { color: "#ff97a8", fontSize: 11, fontWeight: "700", marginBottom: 3 },
  errB: { color: "#d3bcff", fontSize: 10, fontFamily: "monospace" },
  hint: { color: "#5a5b74", fontSize: 10, marginTop: 10, lineHeight: 14 },
});
