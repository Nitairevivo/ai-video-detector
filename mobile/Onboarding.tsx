import React, { useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, Image, ActivityIndicator,
  ScrollView, Linking, Platform, Dimensions, NativeModules,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as SecureStore from "expo-secure-store";
import * as ImagePicker from "expo-image-picker";
import { useOverlay } from "./hooks/useOverlay";

// Kept in sync with App.tsx (small enough to duplicate rather than refactor a
// shared config module across the whole app).
const API = "https://ai-video-detector-production-a305.up.railway.app";
const PREMIUM_URL = "https://web-zeta-ecru-80.vercel.app/dashboard";
const LANG_KEY = "verifai_lang";

const { width, height } = Dimensions.get("window");
const { OverlayModule } = NativeModules;

const C = {
  bg: "#070316", card: "#0e0a24", card2: "#17103a", border: "#ffffff18",
  text: "#f4f2ff", sub: "#a29dc4", faint: "#6b6690",
  violet: "#b061ff", primary: "#a066ff", primaryDeep: "#6d28ff",
  ai: "#ff3d6e", real: "#2ee6a6", gold: "#fbbf24", amber: "#f59e0b",
};
const GRAD = ["#7c3aed", "#d946ef", "#22e3ee"] as const;

type Lang = "he" | "en";
type QuizItem = { url: string; is_ai: boolean };

// Built-in fallback quiz so it works even before the backend /quiz endpoint is
// deployed. Both classes are portrait headshots (subject can't give it away):
// AI = StyleGAN faces (thispersondoesnotexist), real = photographs (randomuser).
const DEFAULT_QUIZ: QuizItem[] = [
  // AI faces (StyleGAN). Each cache-busted URL resolves to a different face.
  { url: "https://thispersondoesnotexist.com/?vqz=1", is_ai: true },
  { url: "https://thispersondoesnotexist.com/?vqz=2", is_ai: true },
  { url: "https://thispersondoesnotexist.com/?vqz=3", is_ai: true },
  { url: "https://thispersondoesnotexist.com/?vqz=4", is_ai: true },
  { url: "https://thispersondoesnotexist.com/?vqz=5", is_ai: true },
  { url: "https://thispersondoesnotexist.com/?vqz=6", is_ai: true },
  // Real photographs (very reliable host).
  { url: "https://randomuser.me/api/portraits/men/32.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/women/44.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/men/75.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/women/68.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/men/11.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/women/22.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/men/59.jpg", is_ai: false },
  { url: "https://randomuser.me/api/portraits/women/90.jpg", is_ai: false },
];

// ─── copy ────────────────────────────────────────────────────────────────────
const L = {
  he: {
    next: "המשך",
    start: "בוא נתחיל",
    skip: "אעשה את זה אחר כך",
    welcomeTitle: "ברוך הבא ל-VerifAI",
    welcomeSub: "VerifAI קורא את הקוד שמאחורי כל סרטון ותמונה — וחושף אם נוצרו ב-AI. בוא נגדיר את זה ב-30 שניות.",
    quizTitle: "קודם — מבחן קטן 🕵️",
    quizSub: "3 תמונות. תנחש: אמיתי או AI? זה יותר קשה ממה שנדמה.",
    quizQuestion: "אמיתי או נוצר ב-AI?",
    real: "📷 אמיתי",
    ai: "🤖 AI",
    correct: "צדקת! ✅",
    wrong: "טעית ❌",
    wasAi: "התמונה נוצרה ב-AI",
    wasReal: "התמונה אמיתית",
    quizNext: "הבא",
    scoreTitle: (n: number) => `צדקת ב-${n} מתוך 3`,
    scoreHigh: "לא רע! אבל גם עין מנוסה מתחילה לפספס — ה-AI משתפר כל יום.",
    scoreLow: "רוב האנשים נכשלים בזה. בדיוק בשביל זה נבנה VerifAI — שלא תצטרך לנחש.",
    proTitle: "👑 עם VerifAI Pro תמיד תדע",
    proSub: "בדיקה אוטומטית של כל סרטון · ללא הגבלה · היסטוריה מלאה · 7 ימים חינם",
    proBtn: "התחל 7 ימים חינם",
    proSkip: "המשך בחינם",
    proFeatures: [
      ["⚡", "זיהוי מיידי", "תוצאה תוך שנייה"],
      ["🔁", "סריקה אוטומטית", "כל סרטון נבדק לבד בזמן גלילה"],
      ["📊", "דו״ח מפורט", "כלי AI, שכבות ניתוח, חתימות"],
      ["♾️", "ללא הגבלה", "בדיקות בלתי מוגבלות"],
    ] as [string, string, string][],
    proPrice: "₪19",
    proPer: "/חודש",
    proTrial: "7 ימים חינם",
    proHeadline: "אל תישאר עם ניחוש",
    overlayTitle: "הפעל את הכפתור הצף",
    overlaySub: "כפתור קטן שיופיע בתוך טיקטוק / אינסטגרם / יוטיוב / טלגרם / וואטסאפ. לחיצה עליו = בדיקה מיידית של הסרטון שעל המסך.",
    overlayBtn: "הפעל את הכפתור",
    overlayOn: "הכפתור פעיל ✓",
    overlayBlocked: "המכשיר חוסם? (שיאומי / רדמי / פוקו)",
    overlayBlockedBody:
      "הגדרות → אפליקציות → VerifAI → הרשאות נוספות → הדלק:\n• 'הצג חלונות קופצים בזמן ריצה ברקע'\n• 'הצג מעל אפליקציות אחרות'\n\nוגם, כדי שלא ייעלם:\n• סוללה → VerifAI → 'ללא הגבלות'\n\nאם המתג לא נדלק בכלל: בתוך מסך פרטי-האפליקציה לחץ ⋮ (3 נקודות) ← 'אפשר הגדרות מוגבלות', ואז נסה שוב.",
    accessTitle: "הפעל זיהוי אוטומטי (חובה)",
    accessWhy:
      "בלי זה הכפתור לא יודע באיזה סרטון אתה צופה — אז הוא נאלץ לצלם מסך (ומקפיץ אותך החוצה). עם נגישות דלוקה: לחיצה אחת קוראת את הקוד האמיתי של הסרטון, בלי לצאת מהאפליקציה, והכפתור מופיע רק באפליקציות הרלוונטיות.",
    accessSteps: "איך מדליקים (30 שניות):",
    accessStep1: "1. לחץ על הכפתור למטה — ייפתחו הגדרות הנגישות",
    accessStep2: "2. מצא את VerifAI ברשימה והדלק",
    accessStep3: "3. אם כתוב \"מוגבל\": חזור למסך פרטי-האפליקציה, לחץ ⋮ ← \"אפשר הגדרות מוגבלות\", ונסה שוב",
    accessBtn: "פתח הגדרות נגישות",
    accessOn: "זיהוי אוטומטי פעיל ✓",
    keepAliveTitle: "⚠️ חשוב! שלא ייכבה אחרי כמה שניות",
    keepAliveBody: "שיאומי / רדמי / פוקו הורגים את הנגישות תוך שניות. כדי שזה יישאר דלוק לתמיד, חובה גם:",
    autostartBtn: "1. אפשר הפעלה אוטומטית (Autostart)",
    autostartNote: "הפעל את VerifAI ברשימה שתיפתח",
    batteryBtn: "2. הסר הגבלת סוללה",
    batteryNote: "בחר 'ללא הגבלות' ל-VerifAI",
    lockNote: "3. במסך האפליקציות האחרונות — נעל את VerifAI (משוך למטה על הכרטיס / מנעול)",
    doneTitle: "הכל מוכן! 🎉",
    doneSub: "פתח טיקטוק / אינסטגרם / טלגרם, לחץ על הכפתור הצף — ותקבל תשובה תוך שניות.",
    doneBtn: "בוא נתחיל לבדוק",
    langBtn: "EN",
  },
  en: {
    next: "Next",
    start: "Let's go",
    skip: "I'll do this later",
    welcomeTitle: "Welcome to VerifAI",
    welcomeSub: "VerifAI reads the code behind every video and image — and reveals if it was made with AI. Let's set it up in 30 seconds.",
    quizTitle: "First — a quick test 🕵️",
    quizSub: "3 images. Guess: real or AI? It's harder than it looks.",
    quizQuestion: "Real or AI-generated?",
    real: "📷 Real",
    ai: "🤖 AI",
    correct: "Correct! ✅",
    wrong: "Wrong ❌",
    wasAi: "This image was AI-generated",
    wasReal: "This image is real",
    quizNext: "Next",
    scoreTitle: (n: number) => `You got ${n} of 3`,
    scoreHigh: "Not bad! But even a trained eye starts to miss — AI improves daily.",
    scoreLow: "Most people fail this. That's exactly why VerifAI exists — so you don't have to guess.",
    proTitle: "👑 With VerifAI Pro you always know",
    proSub: "Auto-check every video · Unlimited · Full history · 7 days free",
    proBtn: "Start 7 days free",
    proSkip: "Continue free",
    proFeatures: [
      ["⚡", "Instant detection", "Results in one second"],
      ["🔁", "Auto-scan", "Every video checked while you scroll"],
      ["📊", "Full report", "AI tools, analysis layers, signatures"],
      ["♾️", "Unlimited", "No daily limits"],
    ] as [string, string, string][],
    proPrice: "₪19",
    proPer: "/mo",
    proTrial: "7 days free",
    proHeadline: "Don't be left guessing",
    overlayTitle: "Turn on the floating button",
    overlaySub: "A small button that appears inside TikTok / Instagram / YouTube / Telegram / WhatsApp. Tap it = instant check of the video on screen.",
    overlayBtn: "Enable the button",
    overlayOn: "Button is active ✓",
    overlayBlocked: "Device blocking it? (Xiaomi / Redmi / Poco)",
    overlayBlockedBody:
      "Settings → Apps → VerifAI → Other permissions → enable:\n• 'Display pop-up windows while running in background'\n• 'Display over other apps'\n\nAnd so it won't vanish:\n• Battery → VerifAI → 'No restrictions'\n\nIf the toggle won't turn on at all: on the app-info screen tap ⋮ (3 dots) → 'Allow restricted settings', then try again.",
    accessTitle: "Enable auto-detection (required)",
    accessWhy:
      "Without it the button can't tell which video you're watching — so it has to screenshot (and bounces you out). With accessibility on: one tap reads the video's real code, without leaving the app, and the button only shows in the relevant apps.",
    accessSteps: "How to enable (30 seconds):",
    accessStep1: "1. Tap the button below — Accessibility settings open",
    accessStep2: "2. Find VerifAI in the list and turn it on",
    accessStep3: "3. If it says \"restricted\": go back to the app-info screen, tap ⋮ → \"Allow restricted settings\", and try again",
    accessBtn: "Open Accessibility settings",
    accessOn: "Auto-detection is active ✓",
    keepAliveTitle: "⚠️ Important! So it doesn't turn off after a few seconds",
    keepAliveBody: "Xiaomi / Redmi / Poco kill accessibility within seconds. To keep it on forever you MUST also:",
    autostartBtn: "1. Allow Autostart",
    autostartNote: "Enable VerifAI in the list that opens",
    batteryBtn: "2. Remove battery restriction",
    batteryNote: "Choose 'No restrictions' for VerifAI",
    lockNote: "3. In Recent apps — lock VerifAI (pull down on the card / lock icon)",
    doneTitle: "All set! 🎉",
    doneSub: "Open TikTok / Instagram / Telegram, tap the floating button — and get an answer in seconds.",
    doneBtn: "Start checking",
    langBtn: "עב",
  },
} as const;

export default function Onboarding({ onDone }: { onDone: () => void }) {
  const [lang, setLang] = useState<Lang>("he");
  const t = L[lang];
  const rtl = lang === "he";
  const isAndroid = Platform.OS === "android";

  useEffect(() => {
    SecureStore.getItemAsync(LANG_KEY).then((l) => {
      if (l === "he" || l === "en") setLang(l);
    }).catch(() => {});
  }, []);
  const toggleLang = () => {
    const nx: Lang = lang === "he" ? "en" : "he";
    setLang(nx);
    SecureStore.setItemAsync(LANG_KEY, nx).catch(() => {});
  };

  const { status, overlayActive, startOverlay, refreshStatus } = useOverlay();

  // The moment accessibility turns on, exempt us from battery optimization —
  // on aggressive OEMs that's a big part of what stops the system from killing
  // the service a few seconds later. Fires once per enable.
  const askedBattery = React.useRef(false);
  useEffect(() => {
    if (status.accessibilityEnabled && !askedBattery.current) {
      askedBattery.current = true;
      try { OverlayModule?.requestIgnoreBatteryOptimizations?.(); } catch {}
    }
  }, [status.accessibilityEnabled]);

  // Ask for media access up front so the floating button can read the actual
  // WhatsApp/Telegram video FILE (they store videos with a .nomedia flag, so we
  // scan the folders directly — which needs this permission).
  useEffect(() => {
    ImagePicker.requestMediaLibraryPermissionsAsync().catch(() => {});
  }, []);

  // ── Quiz: fetch + validate images (only keep ones that actually load) ──
  const [quiz, setQuiz] = useState<QuizItem[]>([]);
  const [quizLoaded, setQuizLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let cand: QuizItem[] = [];
        try {
          const ctrl = new AbortController();
          const to = setTimeout(() => ctrl.abort(), 6000);
          const r = await fetch(`${API}/quiz`, { signal: ctrl.signal });
          clearTimeout(to);
          const d = await r.json();
          if (Array.isArray(d?.items) && d.items.length) cand = d.items;
        } catch {}
        // Backend endpoint not deployed yet / offline → use the built-in set so
        // the quiz still runs.
        if (!cand.length) cand = DEFAULT_QUIZ;
        cand = [...cand].sort(() => Math.random() - 0.5); // vary the set per run
        // Validate images (drop any that don't actually load), gathering a few
        // extra so we can balance the classes.
        const ok: QuizItem[] = [];
        for (const c of cand) {
          if (!c?.url) continue;
          try {
            const good = await Image.prefetch(c.url);
            if (good) ok.push({ url: c.url, is_ai: !!c.is_ai });
          } catch {}
          if (ok.length >= 8) break;
        }
        // A fair quiz must contain BOTH classes — otherwise every answer is the
        // same and it teaches the user nothing. If we can't get a mix, skip it.
        const ai = ok.filter((x) => x.is_ai);
        const real = ok.filter((x) => !x.is_ai);
        let chosen: QuizItem[] = [];
        if (ai.length >= 1 && real.length >= 1 && ok.length >= 3) {
          // Interleave so the sequence alternates classes where possible.
          const a = [...ai], b = [...real];
          while (chosen.length < 3 && (a.length || b.length)) {
            if (a.length && (chosen.length % 2 === 0 || !b.length)) chosen.push(a.shift()!);
            else if (b.length) chosen.push(b.shift()!);
          }
        }
        if (!cancelled) setQuiz(chosen);
      } catch {
        if (!cancelled) setQuiz([]);
      } finally {
        if (!cancelled) setQuizLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // ── Step model ──
  const steps = useMemo(() => {
    const s: string[] = ["welcome"];
    if (quiz.length >= 3) s.push("quiz");
    if (isAndroid) s.push("overlay", "access");
    s.push("done");
    return s;
  }, [quiz.length, isAndroid]);

  const [stepIdx, setStepIdx] = useState(0);
  const step = steps[Math.min(stepIdx, steps.length - 1)];
  const goNext = () => setStepIdx((i) => Math.min(i + 1, steps.length - 1));

  // ── Quiz state ──
  const [qIdx, setQIdx] = useState(0);
  const [answered, setAnswered] = useState<null | boolean>(null); // was the guess correct
  const [score, setScore] = useState(0);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [quizDone, setQuizDone] = useState(false);
  // Any image that fails to actually render is dropped, so a blank tile is never
  // shown. The quiz then runs over whatever loaded.
  const [badUrls, setBadUrls] = useState<Set<string>>(new Set());
  const live = quiz.filter((q) => !badUrls.has(q.url));

  const guess = (guessAI: boolean) => {
    if (answered !== null || !live[qIdx]) return;
    const right = guessAI === live[qIdx].is_ai;
    setAnswered(right);
    setAnsweredCount((n) => n + 1);
    if (right) setScore((n) => n + 1);
  };
  const quizContinue = () => {
    if (qIdx < live.length - 1) {
      setQIdx((i) => i + 1);
      setAnswered(null);
    } else {
      setQuizDone(true);
    }
  };
  const dropImage = (url: string) => {
    setBadUrls((prev) => { const n = new Set(prev); n.add(url); return n; });
  };

  // A single lonely image is a worse experience than no quiz — if fewer than 2
  // images actually loaded (a fair AI-vs-real test needs both), skip the quiz.
  // Also finish/skip if we run out mid-way. Never leave a blank or lonely tile.
  useEffect(() => {
    if (step !== "quiz" || quizDone || !quizLoaded) return;
    if (answeredCount === 0 && live.length < 2) { goNext(); return; }
    if (live.length === 0 || qIdx >= live.length) {
      if (answeredCount > 0) setQuizDone(true);
      else goNext();
    }
  }, [step, quizDone, quizLoaded, live.length, qIdx, answeredCount]);

  const [showOemHelp, setShowOemHelp] = useState(false);

  const align = { textAlign: (rtl ? "right" : "left") as "right" | "left" };
  const writingDir = { writingDirection: (rtl ? "rtl" : "ltr") as "rtl" | "ltr" };

  // ── Renderers ──
  const Header = (
    <View style={st.header}>
      <View style={st.logo}><Text style={st.logoText}>V</Text></View>
      <TouchableOpacity onPress={toggleLang} style={st.langBtn}>
        <Text style={st.langBtnText}>{t.langBtn}</Text>
      </TouchableOpacity>
    </View>
  );

  const Dots = (
    <View style={st.dots}>
      {steps.map((_, i) => (
        <View key={i} style={[st.dot, i === stepIdx && st.dotActive]} />
      ))}
    </View>
  );

  const PrimaryBtn = ({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) => (
    <TouchableOpacity onPress={onPress} activeOpacity={0.85} disabled={disabled} style={{ opacity: disabled ? 0.5 : 1 }}>
      <LinearGradient colors={GRAD} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.primaryBtn}>
        <Text style={st.primaryBtnText}>{label}</Text>
      </LinearGradient>
    </TouchableOpacity>
  );

  let body: React.ReactNode = null;

  if (step === "welcome") {
    body = (
      <View style={st.centerBlock}>
        <Text style={st.bigEmoji}>🛡️</Text>
        <Text style={[st.title, align, writingDir]}>{t.welcomeTitle}</Text>
        <Text style={[st.sub, align, writingDir]}>{t.welcomeSub}</Text>
        <View style={{ height: 24 }} />
        <PrimaryBtn label={t.start} onPress={goNext} />
      </View>
    );
  } else if (step === "quiz" && !quizDone && live[qIdx]) {
    const item = live[qIdx];
    body = (
      <View style={st.quizBlock}>
        <Text style={[st.quizQ, writingDir]}>{t.quizQuestion}</Text>
        <View style={st.quizImgWrap}>
          <Image
            source={{ uri: item.url }}
            style={st.quizImg}
            resizeMode="cover"
            onError={() => dropImage(item.url)}
          />
          <View style={st.quizCounterPill}><Text style={st.quizCounterPillText}>{qIdx + 1} / {live.length}</Text></View>
          {answered !== null && (
            <View style={[st.quizReveal, { backgroundColor: (answered ? C.real : C.ai) + "f2" }]}>
              <Text style={st.quizRevealBig}>{answered ? t.correct : t.wrong}</Text>
              <Text style={st.quizRevealSub}>{item.is_ai ? t.wasAi : t.wasReal}</Text>
            </View>
          )}
        </View>
        {answered === null ? (
          <View style={st.quizBtns}>
            <TouchableOpacity style={[st.guessBtn, { borderColor: C.real }]} onPress={() => guess(false)} activeOpacity={0.8}>
              <Text style={[st.guessText, { color: C.real }]}>{t.real}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[st.guessBtn, { borderColor: C.ai }]} onPress={() => guess(true)} activeOpacity={0.8}>
              <Text style={[st.guessText, { color: C.ai }]}>{t.ai}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <PrimaryBtn label={t.quizNext} onPress={quizContinue} />
        )}
      </View>
    );
  } else if (step === "quiz" && quizDone) {
    const denom = answeredCount || 3;
    body = (
      <View style={st.centerBlock}>
        <Text style={st.bigEmoji}>{score >= denom - 1 ? "🧐" : "🤯"}</Text>
        <Text style={[st.title, { textAlign: "center" }]}>{score} / {denom}</Text>
        <Text style={[st.sub, { textAlign: "center", marginBottom: 4 }]}>{score >= denom - 1 ? t.scoreHigh : t.scoreLow}</Text>

        <View style={st.proCard}>
          <View style={st.proCrown}><Text style={{ fontSize: 26 }}>👑</Text></View>
          <Text style={st.proCardTitle}>VerifAI Pro</Text>
          <Text style={[st.proCardHeadline, { textAlign: "center" }]}>{t.proHeadline}</Text>

          <View style={{ gap: 10, marginTop: 14, marginBottom: 16 }}>
            {t.proFeatures.map((f, i) => (
              <View key={i} style={[st.featRow, { flexDirection: rtl ? "row-reverse" : "row" }]}>
                <Text style={{ fontSize: 18 }}>{f[0]}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={[st.featTitle, align, writingDir]}>{f[1]}</Text>
                  <Text style={[st.featDesc, align, writingDir]}>{f[2]}</Text>
                </View>
                <Text style={st.featCheck}>✓</Text>
              </View>
            ))}
          </View>

          <View style={[st.priceRow, { flexDirection: rtl ? "row-reverse" : "row" }]}>
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "flex-end" }}>
              <Text style={st.priceBig}>{t.proPrice}</Text>
              <Text style={st.pricePer}>{t.proPer}</Text>
            </View>
            <View style={st.trialBadge}><Text style={st.trialBadgeText}>{t.proTrial}</Text></View>
          </View>

          <TouchableOpacity onPress={() => Linking.openURL(PREMIUM_URL).catch(() => {})} activeOpacity={0.85} style={{ marginTop: 14 }}>
            <LinearGradient colors={["#fbbf24", "#f59e0b"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={st.proBtn}>
              <Text style={st.proBtnText}>{t.proBtn}</Text>
            </LinearGradient>
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={goNext}><Text style={st.skipText}>{t.proSkip}</Text></TouchableOpacity>
      </View>
    );
  } else if (step === "overlay") {
    const on = overlayActive || status.overlayPermission;
    body = (
      <View style={st.centerBlock}>
        <Text style={st.bigEmoji}>🎯</Text>
        <Text style={[st.title, align, writingDir]}>{t.overlayTitle}</Text>
        <Text style={[st.sub, align, writingDir]}>{t.overlaySub}</Text>
        <View style={{ height: 18 }} />
        {on ? (
          <View style={st.okPill}><Text style={st.okPillText}>{t.overlayOn}</Text></View>
        ) : (
          <PrimaryBtn label={t.overlayBtn} onPress={async () => { await startOverlay(); try { await OverlayModule?.requestIgnoreBatteryOptimizations?.(); } catch {} refreshStatus(); }} />
        )}
        <TouchableOpacity onPress={() => setShowOemHelp((v) => !v)} style={{ marginTop: 16 }}>
          <Text style={st.linkText}>{t.overlayBlocked}</Text>
        </TouchableOpacity>
        {showOemHelp && <Text style={[st.helpBody, align, writingDir]}>{t.overlayBlockedBody}</Text>}
        <View style={{ height: 20 }} />
        <PrimaryBtn label={t.next} onPress={goNext} />
      </View>
    );
  } else if (step === "access") {
    const on = status.accessibilityEnabled;
    body = (
      <View style={st.centerBlock}>
        <Text style={st.bigEmoji}>⚡</Text>
        <Text style={[st.title, align, writingDir]}>{t.accessTitle}</Text>
        <Text style={[st.sub, align, writingDir]}>{t.accessWhy}</Text>
        <View style={st.stepsCard}>
          <Text style={[st.stepsHead, align, writingDir]}>{t.accessSteps}</Text>
          <Text style={[st.stepLine, align, writingDir]}>{t.accessStep1}</Text>
          <Text style={[st.stepLine, align, writingDir]}>{t.accessStep2}</Text>
          <Text style={[st.stepLine, align, writingDir]}>{t.accessStep3}</Text>
        </View>
        {on ? (
          <View style={st.okPill}><Text style={st.okPillText}>{t.accessOn}</Text></View>
        ) : (
          <PrimaryBtn label={t.accessBtn} onPress={() => { try { OverlayModule?.openAccessibilitySettings?.(); } catch {} }} />
        )}

        {/* Keep-alive: the single most important part on Xiaomi & co. — without
            Autostart + no battery limit, the service is killed within seconds. */}
        <View style={st.keepAliveCard}>
          <Text style={[st.keepAliveTitle, align, writingDir]}>{t.keepAliveTitle}</Text>
          <Text style={[st.keepAliveBody, align, writingDir]}>{t.keepAliveBody}</Text>
          <TouchableOpacity style={st.kaBtn} onPress={() => { try { OverlayModule?.openAutostartSettings?.(); } catch {} }}>
            <Text style={st.kaBtnText}>{t.autostartBtn}</Text>
          </TouchableOpacity>
          <Text style={[st.kaNote, align, writingDir]}>{t.autostartNote}</Text>
          <TouchableOpacity style={st.kaBtn} onPress={() => { try { OverlayModule?.requestIgnoreBatteryOptimizations?.(); } catch {} }}>
            <Text style={st.kaBtnText}>{t.batteryBtn}</Text>
          </TouchableOpacity>
          <Text style={[st.kaNote, align, writingDir]}>{t.batteryNote}</Text>
          <Text style={[st.kaNote, align, writingDir, { marginTop: 8 }]}>{t.lockNote}</Text>
        </View>

        <View style={{ height: 8 }} />
        {on ? (
          <PrimaryBtn label={t.next} onPress={goNext} />
        ) : (
          <TouchableOpacity onPress={goNext}><Text style={st.skipText}>{t.skip}</Text></TouchableOpacity>
        )}
      </View>
    );
  } else if (step === "quiz") {
    // Quiz step but the current image just dropped (onError) and the skip
    // effect hasn't advanced yet — render nothing for this one frame instead of
    // briefly flashing the "done" screen.
    body = <View style={{ height: 200 }} />;
  } else {
    // done
    body = (
      <View style={st.centerBlock}>
        <Text style={st.bigEmoji}>🎉</Text>
        <Text style={[st.title, { textAlign: "center" }]}>{t.doneTitle}</Text>
        <Text style={[st.sub, { textAlign: "center" }]}>{t.doneSub}</Text>
        <View style={{ height: 24 }} />
        <PrimaryBtn label={t.doneBtn} onPress={onDone} />
      </View>
    );
  }

  return (
    <View style={st.root}>
      {/* Subtle, professional backdrop — a faint violet glow at the top fading to
          near-black, instead of a loud full-screen purple gradient. */}
      <LinearGradient colors={["#12102a", "#08061a", "#060312"]} locations={[0, 0.4, 1]} style={StyleSheet.absoluteFill} />
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        {Header}
        {body}
      </ScrollView>
      {Dots}
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { padding: 22, paddingBottom: 60, flexGrow: 1, justifyContent: "center" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  logo: { width: 44, height: 44, borderRadius: 13, backgroundColor: C.primary, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: "#ffffff33" },
  logoText: { color: "#fff", fontSize: 24, fontWeight: "900" },
  langBtn: { backgroundColor: C.card, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: C.border },
  langBtnText: { color: C.sub, fontSize: 12, fontWeight: "800" },
  centerBlock: { gap: 10, paddingVertical: 12 },
  bigEmoji: { fontSize: 56, textAlign: "center", marginBottom: 6 },
  title: { color: C.text, fontSize: 26, fontWeight: "900", letterSpacing: -0.5 },
  sub: { color: C.sub, fontSize: 15, lineHeight: 22 },
  primaryBtn: { borderRadius: 16, paddingVertical: 16, alignItems: "center", justifyContent: "center" },
  primaryBtnText: { color: "#fff", fontSize: 17, fontWeight: "800" },
  skipText: { color: C.faint, fontSize: 14, fontWeight: "600", textAlign: "center", marginTop: 14, textDecorationLine: "underline" },
  linkText: { color: C.violet, fontSize: 14, fontWeight: "700", textAlign: "center" },
  helpBody: { color: C.sub, fontSize: 13, lineHeight: 20, marginTop: 10, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border },
  dots: { flexDirection: "row", justifyContent: "center", gap: 7, paddingBottom: 22 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#ffffff22" },
  dotActive: { width: 22, backgroundColor: C.primary },
  // quiz — full-bleed, near-full-screen image
  quizBlock: { gap: 16, paddingVertical: 2 },
  quizImgWrap: {
    width: width,                       // edge-to-edge (breaks out of scroll padding)
    height: Math.min(height * 0.62, width * 1.5),
    marginHorizontal: -22,
    overflow: "hidden", backgroundColor: C.card, alignSelf: "center",
  },
  quizImg: { width: "100%", height: "100%" },
  quizCounterPill: { position: "absolute", top: 14, left: 14, backgroundColor: "#00000099", borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5 },
  quizCounterPillText: { color: "#fff", fontSize: 13, fontWeight: "800" },
  quizReveal: { position: "absolute", left: 0, right: 0, bottom: 0, paddingVertical: 22, alignItems: "center" },
  quizRevealBig: { color: "#fff", fontSize: 28, fontWeight: "900" },
  quizRevealSub: { color: "#ffffffee", fontSize: 15, fontWeight: "700", marginTop: 3 },
  quizQ: { color: C.text, fontSize: 21, fontWeight: "800", textAlign: "center" },
  quizBtns: { flexDirection: "row", gap: 12, paddingHorizontal: 2 },
  guessBtn: { flex: 1, borderWidth: 1.5, borderRadius: 14, paddingVertical: 17, alignItems: "center", backgroundColor: "#ffffff08" },
  guessText: { fontSize: 17, fontWeight: "800" },
  // pro pricing screen
  proCard: { backgroundColor: C.card2, borderRadius: 22, padding: 20, marginTop: 18, borderWidth: 1, borderColor: C.gold + "55" },
  proCrown: { alignSelf: "center", width: 52, height: 52, borderRadius: 16, backgroundColor: C.gold + "1f", alignItems: "center", justifyContent: "center", marginBottom: 6 },
  proCardTitle: { color: C.gold, fontSize: 22, fontWeight: "900", textAlign: "center" },
  proCardHeadline: { color: C.sub, fontSize: 14, marginTop: 2 },
  featRow: { alignItems: "center", gap: 12 },
  featTitle: { color: C.text, fontSize: 15, fontWeight: "800" },
  featDesc: { color: C.sub, fontSize: 12, marginTop: 1 },
  featCheck: { color: C.real, fontSize: 16, fontWeight: "900" },
  priceRow: { alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  priceBig: { color: C.text, fontSize: 34, fontWeight: "900" },
  pricePer: { color: C.sub, fontSize: 15, fontWeight: "700", marginBottom: 6, marginHorizontal: 2 },
  trialBadge: { backgroundColor: C.real + "22", borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: C.real + "66" },
  trialBadgeText: { color: C.real, fontSize: 13, fontWeight: "800" },
  proBtn: { borderRadius: 14, paddingVertical: 15, alignItems: "center" },
  proBtnText: { color: "#1a1203", fontSize: 16, fontWeight: "900" },
  // ok pill
  okPill: { backgroundColor: C.real + "22", borderColor: C.real, borderWidth: 1.5, borderRadius: 16, paddingVertical: 15, alignItems: "center" },
  okPillText: { color: C.real, fontSize: 16, fontWeight: "800" },
  // steps
  stepsCard: { backgroundColor: C.card, borderRadius: 16, padding: 16, marginVertical: 16, borderWidth: 1, borderColor: C.border, gap: 8 },
  stepsHead: { color: C.text, fontSize: 15, fontWeight: "800", marginBottom: 2 },
  stepLine: { color: C.sub, fontSize: 14, lineHeight: 21 },
  // keep-alive (anti-kill on aggressive OEMs)
  keepAliveCard: { backgroundColor: C.amber + "14", borderRadius: 16, padding: 16, marginTop: 16, borderWidth: 1, borderColor: C.amber + "55" },
  keepAliveTitle: { color: C.amber, fontSize: 15, fontWeight: "900" },
  keepAliveBody: { color: C.sub, fontSize: 13, lineHeight: 19, marginTop: 4, marginBottom: 10 },
  kaBtn: { backgroundColor: C.card2, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 14, marginTop: 8, borderWidth: 1, borderColor: C.amber + "44" },
  kaBtnText: { color: C.text, fontSize: 14, fontWeight: "800", textAlign: "center" },
  kaNote: { color: C.faint, fontSize: 12, marginTop: 4, lineHeight: 17 },
});
