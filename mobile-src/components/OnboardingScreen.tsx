import React, { useState, useRef, useEffect } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Animated,
  Dimensions, Platform, Linking, NativeModules, AppState,
} from "react-native";

const { width } = Dimensions.get("window");
const { OverlayModule } = NativeModules;

type Step = {
  emoji: string;
  title: string;
  desc: string;
  btnLabel: string;
  check: () => Promise<boolean>;
  open: () => void;
};

const STEPS: Step[] = [
  {
    emoji: "🔍",
    title: "כפתור צף מעל כל אפליקציה",
    desc: 'לחץ "הפעל" ← בחר VerifAI ← הפעל את המתג',
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
    desc: 'לחץ "הפעל" ← VerifAI Auto-Detect ← הפעל את המתג\nכך הכפתור יופיע רק בתוך TikTok, Instagram וכו\' ויביא תשובה בלחיצה',
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
    emoji: "✅",
    title: "הכל מוכן!",
    desc: "פתח TikTok, גלול על סרטון — התוצאה תופיע אוטומטית תוך שניות",
    btnLabel: "התחל",
    check: async () => true,
    open: () => {},
  },
];

type Props = {
  onDone: () => void;
};

export function OnboardingScreen({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [stepDone, setStepDone] = useState([false, false, false]);
  const slideAnim = useRef(new Animated.Value(0)).current;
  const checkAnim = useRef(new Animated.Value(0)).current;

  const current = STEPS[step];

  // When app comes back to foreground, re-check permission
  // Auto-request permission when step appears
  useEffect(() => {
    if (step < STEPS.length - 1) {
      const timer = setTimeout(() => {
        STEPS[step].open();
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [step]);

  // Check permission when app returns from settings
  useEffect(() => {
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      const done = await STEPS[step].check();
      if (done) {
        setStepDone((prev) => {
          const next = [...prev];
          next[step] = true;
          return next;
        });
        Animated.spring(checkAnim, { toValue: 1, useNativeDriver: true, tension: 80, friction: 6 }).start();
        // Auto-advance after short delay
        if (step < STEPS.length - 1) {
          setTimeout(() => goNext(), 1200);
        }
      }
    });
    return () => sub.remove();
  }, [step]);

  const goNext = () => {
    if (step === STEPS.length - 1) {
      onDone();
      return;
    }
    Animated.timing(slideAnim, { toValue: -width, duration: 250, useNativeDriver: true }).start(() => {
      setStep((s) => s + 1);
      checkAnim.setValue(0);
      slideAnim.setValue(width);
      Animated.timing(slideAnim, { toValue: 0, duration: 250, useNativeDriver: true }).start();
    });
  };

  const handleBtn = () => {
    if (step === STEPS.length - 1) { onDone(); return; }
    current.open();
    // Advancing happens via the AppState listener once the permission
    // is actually granted, or manually via the skip button.
  };

  const isLast = step === STEPS.length - 1;
  const isDone = stepDone[step];

  return (
    <View style={s.root}>
      {/* Progress dots */}
      <View style={s.dots}>
        {STEPS.map((_, i) => (
          <View key={i} style={[s.dot, i === step && s.dotActive, i < step && s.dotDone]} />
        ))}
      </View>

      <Animated.View style={[s.card, { transform: [{ translateX: slideAnim }] }]}>
        {/* Emoji */}
        <View style={s.emojiWrap}>
          <Text style={s.emoji}>{current.emoji}</Text>
          {isDone && (
            <Animated.View style={[s.checkBadge, { transform: [{ scale: checkAnim }] }]}>
              <Text style={s.checkBadgeText}>✓</Text>
            </Animated.View>
          )}
        </View>

        {/* Step number */}
        {!isLast && (
          <Text style={s.stepLabel}>שלב {step + 1} מתוך {STEPS.length - 1}</Text>
        )}

        <Text style={s.title}>{current.title}</Text>
        <Text style={s.desc}>{current.desc}</Text>

        {/* Main action button */}
        {!isLast && (
          <TouchableOpacity style={s.actionBtn} onPress={handleBtn} activeOpacity={0.85}>
            <Text style={s.actionBtnText}>{current.btnLabel} →</Text>
          </TouchableOpacity>
        )}

        {/* Done state or skip */}
        {isDone && !isLast && (
          <TouchableOpacity style={s.nextBtn} onPress={goNext}>
            <Text style={s.nextBtnText}>הרשאה אושרה ✓ — המשך</Text>
          </TouchableOpacity>
        )}

        {!isDone && !isLast && step < STEPS.length - 1 && (
          <TouchableOpacity style={s.skipBtn} onPress={goNext}>
            <Text style={s.skipText}>דלג בינתיים</Text>
          </TouchableOpacity>
        )}

        {/* Final step */}
        {isLast && (
          <View style={s.finalWrap}>
            {["TikTok", "Instagram", "YouTube", "Facebook", "Snapchat"].map((app) => (
              <View key={app} style={s.appPill}>
                <Text style={s.appPillText}>{app}</Text>
              </View>
            ))}
            <TouchableOpacity style={[s.actionBtn, { marginTop: 24, width: "100%" }]} onPress={onDone}>
              <Text style={s.actionBtnText}>סיים והתחל →</Text>
            </TouchableOpacity>
          </View>
        )}
      </Animated.View>

      {/* How it works */}
      {!isLast && (
        <View style={s.howWrap}>
          <Text style={s.howTitle}>איך זה עובד?</Text>
          {step === 0 && <Text style={s.howText}>כפתור 🔍 קבוע יופיע למעלה בצד — רק בתוך אפליקציות הסרטונים</Text>}
          {step === 1 && <Text style={s.howText}>לחיצה על הכפתור שולפת את הסרטון הנוכחי ומחזירה תשובה</Text>}
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1, backgroundColor: "#06060f",
    justifyContent: "center", alignItems: "center",
    padding: 24,
  },
  dots: { flexDirection: "row", gap: 8, marginBottom: 32 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#1a1a2e" },
  dotActive: { backgroundColor: "#6366f1", width: 24 },
  dotDone: { backgroundColor: "#22c55e" },

  card: {
    width: "100%", backgroundColor: "#0d0d1e",
    borderRadius: 28, padding: 28,
    borderWidth: 1, borderColor: "#ffffff0a",
    alignItems: "center", gap: 16,
  },

  emojiWrap: { position: "relative", marginBottom: 8 },
  emoji: { fontSize: 72 },
  checkBadge: {
    position: "absolute", bottom: -4, right: -4,
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: "#22c55e", alignItems: "center", justifyContent: "center",
    borderWidth: 2, borderColor: "#0d0d1e",
  },
  checkBadgeText: { color: "#fff", fontSize: 14, fontWeight: "800" },

  stepLabel: { color: "#6366f1", fontSize: 11, fontWeight: "700", letterSpacing: 1.5 },
  title: { color: "#fff", fontSize: 22, fontWeight: "800", textAlign: "center", lineHeight: 28 },
  desc: { color: "#9ca3af", fontSize: 14, textAlign: "center", lineHeight: 22 },

  actionBtn: {
    backgroundColor: "#4f46e5", borderRadius: 16, paddingVertical: 16,
    paddingHorizontal: 32, alignItems: "center",
    shadowColor: "#4f46e5", shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.5, shadowRadius: 16, elevation: 10,
    width: "100%",
  },
  actionBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },

  nextBtn: {
    backgroundColor: "#14532d", borderRadius: 14, paddingVertical: 12,
    paddingHorizontal: 24, alignItems: "center", width: "100%",
    borderWidth: 1, borderColor: "#22c55e44",
  },
  nextBtnText: { color: "#22c55e", fontSize: 14, fontWeight: "600" },

  skipBtn: { paddingVertical: 8 },
  skipText: { color: "#374151", fontSize: 13 },

  finalWrap: { width: "100%", alignItems: "center", gap: 12 },
  appPill: {
    backgroundColor: "#111122", borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 6,
    borderWidth: 1, borderColor: "#ffffff0a",
  },
  appPillText: { color: "#6b7280", fontSize: 13 },

  howWrap: { marginTop: 24, alignItems: "center", gap: 6 },
  howTitle: { color: "#374151", fontSize: 11, fontWeight: "600", letterSpacing: 1 },
  howText: { color: "#1f2937", fontSize: 13, textAlign: "center" },
});
