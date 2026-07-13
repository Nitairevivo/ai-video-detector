import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Animated, Easing, Platform } from "react-native";

// ─── DemoReel — the in-app "how it works" animation ──────────────────────────
// A looping, native mini-demo: a video plays, the floating VerifAI button scans
// it, and a red "AI-generated" verdict lands. It's the tutorial video, built in
// RN so it needs no media file and never buffers. Purely decorative — respects
// reduce-motion by holding the final verdict frame.

type Props = { lang: "he" | "en" };

const C = {
  screen: "#08060f", panel: "#161027",
  violet: "#a066ff", violetDeep: "#6d28ff",
  alarm: "#ff2d6b", scan: "#38e6f0", text: "#efeaf8", muted: "#8f89a8",
};

const STR = {
  he: {
    sponsored: "ממומן · השקעה",
    videoLine: "300% תשואה מובטחת 🚀",
    stateIdle: "מזהה סרטון…",
    stateScan: "סורק · C2PA · תוויות AI…",
    stateDone: "⚠ נוצר ב-AI · 96%",
    badge: "נוצר ב-AI",
    verdict: "🤖 סרטון מזויף",
    caption: "ככה זה נראה: לחיצה אחת על הכפתור הצף — ותשובה תוך שניות.",
  },
  en: {
    sponsored: "Sponsored · Investment",
    videoLine: "300% guaranteed returns 🚀",
    stateIdle: "Detecting video…",
    stateScan: "Scanning · C2PA · AI labels…",
    stateDone: "⚠ AI-generated · 96%",
    badge: "AI-GENERATED",
    verdict: "🤖 Fake video",
    caption: "This is it: one tap on the floating button — an answer in seconds.",
  },
};

export function DemoReel({ lang }: Props) {
  const rtl = lang === "he";
  const t = STR[lang];

  const sweepY = useRef(new Animated.Value(-40)).current;
  const sweepOpacity = useRef(new Animated.Value(0)).current;
  const ring = useRef(new Animated.Value(0)).current;
  const verdictOpacity = useRef(new Animated.Value(0)).current;
  const verdictScale = useRef(new Animated.Value(0.6)).current;
  const meter = useRef(new Animated.Value(0)).current;
  const [phase, setPhase] = useState<"idle" | "scan" | "done">("idle");

  useEffect(() => {
    const reduce = false; // RN has no media query; keep the loop, it's gentle.
    let cancelled = false;

    const ringLoop = Animated.loop(
      Animated.timing(ring, { toValue: 1, duration: 1400, easing: Easing.out(Easing.ease), useNativeDriver: true })
    );

    const runCycle = () => {
      if (cancelled) return;
      // reset
      sweepY.setValue(-40); sweepOpacity.setValue(0);
      verdictOpacity.setValue(0); verdictScale.setValue(0.6); meter.setValue(0);
      setPhase("idle");

      const seq = Animated.sequence([
        Animated.delay(900),
        // scan
        Animated.parallel([
          Animated.timing(sweepOpacity, { toValue: 1, duration: 150, useNativeDriver: true }),
          Animated.timing(sweepY, { toValue: 250, duration: 1700, easing: Easing.inOut(Easing.cubic), useNativeDriver: true }),
        ]),
        Animated.timing(sweepOpacity, { toValue: 0, duration: 150, useNativeDriver: true }),
        // verdict slam
        Animated.parallel([
          Animated.timing(verdictOpacity, { toValue: 1, duration: 200, useNativeDriver: true }),
          Animated.spring(verdictScale, { toValue: 1, tension: 120, friction: 7, useNativeDriver: true }),
          Animated.timing(meter, { toValue: 1, duration: 900, delay: 150, easing: Easing.out(Easing.cubic), useNativeDriver: false }),
        ]),
      ]);

      setPhase("idle");
      setTimeout(() => !cancelled && setPhase("scan"), 900);
      setTimeout(() => !cancelled && setPhase("done"), 2750);
      seq.start(() => {
        setTimeout(runCycle, 3200); // hold the verdict, then loop
      });
    };

    ringLoop.start();
    runCycle();
    return () => { cancelled = true; ringLoop.stop(); };
  }, []);

  const ringStyle = {
    opacity: ring.interpolate({ inputRange: [0, 1], outputRange: [0.6, 0] }),
    transform: [{ scale: ring.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1.55] }) }],
  };
  const meterW = meter.interpolate({ inputRange: [0, 1], outputRange: ["0%", "96%"] });
  const stateText = phase === "idle" ? t.stateIdle : phase === "scan" ? t.stateScan : t.stateDone;

  return (
    <View style={s.wrap}>
      <View style={s.phone}>
        <View style={s.screen}>
          {/* the "video" */}
          <View style={s.figure}><Text style={s.figureEmoji}>👤</Text></View>
          <View style={[s.lower, { alignItems: rtl ? "flex-end" : "flex-start" }]}>
            <Text style={s.lowerK}>{t.sponsored}</Text>
            <Text style={s.lowerT}>{t.videoLine}</Text>
          </View>

          {/* floating button */}
          <View style={[s.fab, rtl ? { left: 12 } : { right: 12 }]}>
            {phase === "scan" && <Animated.View style={[s.ring, ringStyle]} />}
            <Text style={s.fabText}>AI?</Text>
          </View>

          {/* scan sweep */}
          <Animated.View style={[s.sweep, { opacity: sweepOpacity, transform: [{ translateY: sweepY }] }]} />

          {/* verdict card */}
          <Animated.View style={[s.verdict, { opacity: verdictOpacity, transform: [{ scale: verdictScale }] }]}>
            <Text style={s.pct}>96%</Text>
            <View style={s.badge}><View style={s.dot} /><Text style={s.badgeText}>{t.badge}</Text></View>
            <Text style={s.verdictTitle}>{t.verdict}</Text>
            <View style={s.meterTrack}><Animated.View style={[s.meterFill, { width: meterW }]} /></View>
          </Animated.View>
        </View>
      </View>

      <Text style={[s.state, { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" }]}>{stateText}</Text>
      <Text style={s.caption}>{t.caption}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: "center", gap: 12, paddingVertical: 8 },
  phone: {
    width: 180, height: 320, borderRadius: 28, padding: 8,
    backgroundColor: "#1c1533",
    shadowColor: "#000", shadowOffset: { width: 0, height: 20 }, shadowOpacity: 0.5, shadowRadius: 30, elevation: 14,
    borderWidth: 1, borderColor: "rgba(160,102,255,.28)",
  },
  screen: { flex: 1, borderRadius: 21, overflow: "hidden", backgroundColor: C.screen },
  figure: {
    position: "absolute", top: 60, alignSelf: "center",
    width: 78, height: 78, borderRadius: 39, backgroundColor: "#241a3a",
    alignItems: "center", justifyContent: "center",
  },
  figureEmoji: { fontSize: 40, opacity: 0.85 },
  lower: {
    position: "absolute", left: 12, right: 12, bottom: 44,
    backgroundColor: "rgba(255,45,107,.12)", borderColor: "rgba(255,45,107,.35)",
    borderWidth: 1, borderRadius: 10, padding: 9,
  },
  lowerK: { color: C.alarm, fontSize: 9, fontWeight: "700", fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  lowerT: { color: C.text, fontSize: 13, fontWeight: "800", marginTop: 2 },
  fab: {
    position: "absolute", top: 48, width: 42, height: 42, borderRadius: 21,
    backgroundColor: C.violetDeep, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(255,255,255,.28)",
    shadowColor: C.violetDeep, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.6, shadowRadius: 12, elevation: 10,
  },
  fabText: { color: "#fff", fontSize: 12, fontWeight: "900" },
  ring: { position: "absolute", top: -6, left: -6, right: -6, bottom: -6, borderRadius: 27, borderWidth: 2, borderColor: C.violet },
  sweep: {
    position: "absolute", left: 0, right: 0, top: 0, height: 70,
    backgroundColor: "rgba(56,230,240,.16)", borderBottomWidth: 2, borderBottomColor: C.scan,
  },
  verdict: {
    position: "absolute", left: 12, right: 12, top: "34%",
    borderRadius: 14, padding: 12,
    backgroundColor: "rgba(20,6,14,.92)", borderWidth: 1, borderColor: "rgba(255,45,107,.55)",
  },
  pct: { position: "absolute", top: 10, right: 10, color: C.alarm, fontSize: 18, fontWeight: "900", fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  badge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", backgroundColor: "rgba(255,45,107,.14)", borderRadius: 100, paddingHorizontal: 9, paddingVertical: 3 },
  dot: { width: 5, height: 5, borderRadius: 3, backgroundColor: C.alarm },
  badgeText: { color: C.alarm, fontSize: 9, fontWeight: "800", fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  verdictTitle: { color: C.text, fontSize: 15, fontWeight: "900", marginTop: 8 },
  meterTrack: { height: 6, borderRadius: 3, backgroundColor: "rgba(255,255,255,.08)", overflow: "hidden", marginTop: 10 },
  meterFill: { height: 6, borderRadius: 3, backgroundColor: C.alarm },
  state: { color: "#5f5a78", fontSize: 12 },
  caption: { color: C.muted, fontSize: 13, textAlign: "center", paddingHorizontal: 20, lineHeight: 19 },
});
