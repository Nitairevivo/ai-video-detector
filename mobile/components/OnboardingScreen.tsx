import React, { useState, useRef, useEffect } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Animated,
  Dimensions, Platform, Linking, NativeModules, AppState, Easing,
} from "react-native";

const { width } = Dimensions.get("window");
const { OverlayModule } = NativeModules;

const C = {
  bg: "#05060e",
  card: "#0c0e1d",
  border: "#ffffff10",
  text: "#f1f2f8",
  sub: "#9aa0b8",
  faint: "#565c78",
  primary: "#7c6cff",
  primaryDeep: "#4f46e5",
  real: "#10b981",
};

type Step = {
  emoji: string;
  title: string;
  desc: string;
  how: string;
  btnLabel: string;
  check: () => Promise<boolean>;
  open: () => void;
};

const STEPS: Step[] = [
  {
    emoji: "🔍",
    title: "כפתור צף מעל כל אפליקציה",
    desc: "כפתור VerifAI קטן יופיע בתוך TikTok, Instagram ו-YouTube — לחיצה אחת בודקת את הסרטון שמולך",
    how: 'במסך שייפתח: בחר VerifAI ← הפעל את המתג ← חזור לכאן',
    btnLabel: "הפעל הרשאה",
    check: async () => {
      if (Platform.OS !== "android" || !OverlayModule) return true;
      return await OverlayModule.hasPermission();
    },
    open: () => {
      if (Platform.OS === "android" && OverlayModule) {
        OverlayModule.requestPermission();
      }
    },
  },
  {
    emoji: "⚡",
    title: "זיהוי בלחיצה אחת",
    desc: "שירות הנגישות שולף את הקישור של הסרטון שמוצג על המסך — בלי להעתיק כלום ידנית",
    how: 'במסך שייפתח: VerifAI Auto-Detect ← הפעל את המתג ← חזור לכאן',
    btnLabel: "הפעל נגישות",
    check: async () => {
      if (Platform.OS !== "android" || !OverlayModule?.isAccessibilityEnabled) return false;
      try { return await OverlayModule.isAccessibilityEnabled(); } catch { return false; }
    },
    open: () => {
      if (Platform.OS === "android" && OverlayModule?.openAccessibilitySettings) {
        OverlayModule.openAccessibilitySettings().catch(() => Linking.openSettings());
      } else {
        Linking.openSettings();
      }
    },
  },
  {
    emoji: "🛡️",
    title: "הכל מוכן!",
    desc: "פתח TikTok, גלול לסרטון ולחץ על כפתור VerifAI — התוצאה תופיע תוך שניות",
    how: "",
    btnLabel: "התחל",
    check: async () => true,
    open: () => {},
  },
];

type Props = { onDone: () => void };

export function OnboardingScreen({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [stepDone, setStepDone] = useState([false, false, false]);
  const slideAnim = useRef(new Animated.Value(0)).current;
  const checkAnim = useRef(new Animated.Value(0)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;

  const current = STEPS[step];

  // Soft breathing glow behind the emoji
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(glowAnim, { toValue: 1, duration: 1600, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      Animated.timing(glowAnim, { toValue: 0, duration: 1600, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, []);

  // When a step appears: if its permission is ALREADY granted, mark it done
  // instead of bouncing the user to Settings for nothing. Otherwise open
  // Settings for them after a short beat.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (step >= STEPS.length - 1) return;
      const already = await STEPS[step].check().catch(() => false);
      if (cancelled) return;
      if (already) {
        markDone();
      } else {
        const timer = setTimeout(() => STEPS[step].open(), 800);
        return () => clearTimeout(timer);
      }
    })();
    return () => { cancelled = true; };
  }, [step]);

  // Re-check when returning from Settings
  useEffect(() => {
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      const done = await STEPS[step].check();
      if (done) markDone();
    });
    return () => sub.remove();
  }, [step]);

  const markDone = () => {
    setStepDone((prev) => {
      if (prev[step]) return prev;
      const next = [...prev];
      next[step] = true;
      return next;
    });
    Animated.spring(checkAnim, { toValue: 1, useNativeDriver: true, tension: 80, friction: 6 }).start();
    if (step < STEPS.length - 1) {
      setTimeout(() => goNext(), 1100);
    }
  };

  const goNext = () => {
    if (step === STEPS.length - 1) { onDone(); return; }
    Animated.timing(slideAnim, { toValue: -width, duration: 220, useNativeDriver: true }).start(() => {
      setStep((s2) => s2 + 1);
      checkAnim.setValue(0);
      slideAnim.setValue(width);
      Animated.timing(slideAnim, { toValue: 0, duration: 220, useNativeDriver: true }).start();
    });
  };

  const handleBtn = () => {
    if (step === STEPS.length - 1) { onDone(); return; }
    current.open();
  };

  const isLast = step === STEPS.length - 1;
  const isDone = stepDone[step];

  return (
    <View style={s.root}>
      {/* Brand */}
      <View style={s.brand}>
        <View style={s.logoMark}><Text style={s.logoMarkText}>V</Text></View>
        <Text style={s.brandName}>VerifAI</Text>
      </View>

      {/* Progress */}
      <View style={s.progress}>
        {STEPS.map((_, i) => (
          <View key={i} style={[s.seg, i < step && s.segDone, i === step && s.segActive]} />
        ))}
      </View>

      <Animated.View style={[s.card, { transform: [{ translateX: slideAnim }] }]}>
        <View style={s.emojiWrap}>
          <Animated.View style={[s.emojiGlow, {
            opacity: glowAnim.interpolate({ inputRange: [0, 1], outputRange: [0.25, 0.6] }),
            transform: [{ scale: glowAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.15] }) }],
          }]} />
          <Text style={s.emoji}>{current.emoji}</Text>
          {isDone && (
            <Animated.View style={[s.checkBadge, { transform: [{ scale: checkAnim }] }]}>
              <Text style={s.checkBadgeText}>✓</Text>
            </Animated.View>
          )}
        </View>

        {!isLast && <Text style={s.stepLabel}>שלב {step + 1} מתוך {STEPS.length - 1}</Text>}

        <Text style={s.title}>{current.title}</Text>
        <Text style={s.desc}>{current.desc}</Text>
        {!!current.how && !isDone && (
          <View style={s.howBox}><Text style={s.howBoxText}>{current.how}</Text></View>
        )}

        {!isLast && !isDone && (
          <TouchableOpacity style={s.actionBtn} onPress={handleBtn} activeOpacity={0.85}>
            <Text style={s.actionBtnText}>{current.btnLabel}</Text>
          </TouchableOpacity>
        )}

        {isDone && !isLast && (
          <TouchableOpacity style={s.nextBtn} onPress={goNext}>
            <Text style={s.nextBtnText}>הרשאה אושרה ✓ — המשך</Text>
          </TouchableOpacity>
        )}

        {!isDone && !isLast && (
          <TouchableOpacity style={s.skipBtn} onPress={goNext}>
            <Text style={s.skipText}>דלג בינתיים</Text>
          </TouchableOpacity>
        )}

        {isLast && (
          <View style={s.finalWrap}>
            <View style={s.pillsRow}>
              {["TikTok", "Instagram", "YouTube", "Facebook", "X"].map((app) => (
                <View key={app} style={s.appPill}>
                  <Text style={s.appPillText}>{app}</Text>
                </View>
              ))}
            </View>
            <TouchableOpacity style={[s.actionBtn, { marginTop: 20 }]} onPress={onDone}>
              <Text style={s.actionBtnText}>סיים והתחל</Text>
            </TouchableOpacity>
          </View>
        )}
      </Animated.View>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1, backgroundColor: C.bg,
    justifyContent: "center", alignItems: "center",
    padding: 24,
  },
  brand: { flexDirection: "row-reverse", alignItems: "center", gap: 10, marginBottom: 28 },
  logoMark: {
    width: 36, height: 36, borderRadius: 11, alignItems: "center", justifyContent: "center",
    backgroundColor: C.primaryDeep, borderWidth: 1, borderColor: "#ffffff2e",
  },
  logoMarkText: { color: "#fff", fontSize: 18, fontWeight: "900" },
  brandName: { color: C.text, fontSize: 20, fontWeight: "900", letterSpacing: -0.5 },

  progress: { flexDirection: "row", gap: 6, marginBottom: 28, width: "70%" },
  seg: { flex: 1, height: 4, borderRadius: 2, backgroundColor: "#1a1c30" },
  segActive: { backgroundColor: C.primary },
  segDone: { backgroundColor: C.real },

  card: {
    width: "100%", backgroundColor: C.card,
    borderRadius: 26, padding: 26,
    borderWidth: 1, borderColor: C.border,
    alignItems: "center", gap: 14,
  },

  emojiWrap: { position: "relative", marginBottom: 6, alignItems: "center", justifyContent: "center" },
  emojiGlow: {
    position: "absolute", width: 110, height: 110, borderRadius: 55,
    backgroundColor: C.primaryDeep,
  },
  emoji: { fontSize: 64 },
  checkBadge: {
    position: "absolute", bottom: -2, right: -6,
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: C.real, alignItems: "center", justifyContent: "center",
    borderWidth: 2, borderColor: C.card,
  },
  checkBadgeText: { color: "#fff", fontSize: 14, fontWeight: "800" },

  stepLabel: { color: C.primary, fontSize: 11, fontWeight: "700", letterSpacing: 1.5 },
  title: { color: C.text, fontSize: 22, fontWeight: "800", textAlign: "center", lineHeight: 28 },
  desc: { color: C.sub, fontSize: 14, textAlign: "center", lineHeight: 22 },

  howBox: {
    backgroundColor: "#ffffff08", borderRadius: 14, padding: 12,
    borderWidth: 1, borderColor: C.border, width: "100%",
  },
  howBoxText: { color: C.sub, fontSize: 12, textAlign: "center", lineHeight: 19 },

  actionBtn: {
    backgroundColor: C.primaryDeep, borderRadius: 16, paddingVertical: 16,
    alignItems: "center", width: "100%",
    shadowColor: C.primaryDeep, shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.5, shadowRadius: 16, elevation: 10,
  },
  actionBtnText: { color: "#fff", fontSize: 16, fontWeight: "800" },

  nextBtn: {
    backgroundColor: "#0b2a1c", borderRadius: 14, paddingVertical: 13,
    alignItems: "center", width: "100%",
    borderWidth: 1, borderColor: C.real + "44",
  },
  nextBtnText: { color: C.real, fontSize: 14, fontWeight: "700" },

  skipBtn: { paddingVertical: 6 },
  skipText: { color: C.faint, fontSize: 13 },

  finalWrap: { width: "100%", alignItems: "center" },
  pillsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "center" },
  appPill: {
    backgroundColor: "#12142a", borderRadius: 18,
    paddingHorizontal: 14, paddingVertical: 6,
    borderWidth: 1, borderColor: C.border,
  },
  appPillText: { color: C.sub, fontSize: 13 },
});
