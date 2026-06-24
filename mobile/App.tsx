import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  View, Text, StyleSheet, Animated, TouchableOpacity,
  SafeAreaView, StatusBar, ScrollView, Alert, Vibration,
  Platform, Switch, Modal, Dimensions, Linking, I18nManager,
} from "react-native";

// ─── i18n — Hebrew / English ──────────────────────────────────────────────────
type Lang = "he" | "en";

const T = {
  he: {
    poweredBy: "מופעל על ידי AI",
    noVideos: "לא נסרקו סרטונים עדיין",
    noVideosHint: {
      android: "השתמש בכפתור 🔍 הצף בזמן גלילה ב-TikTok",
      ios: "שתף סרטון מ-TikTok כדי להתחיל",
    },
    headerSub: {
      android: "כפתור 🔍 צף מעל כל אפליקציה — זהה סרטוני AI תוך שניות",
      ios: "שתף סרטון מ-TikTok או Instagram לזיהוי מיידי",
    },
    overlayCard: "כפתור צף אוטומטי",
    overlaySub: "מזהה סרטונים אוטומטית בזמן גלילה",
    iosCard: "📱 איך להשתמש ב-iPhone",
    iosSteps: [
      "פתח TikTok, Instagram או YouTube",
      "לחץ Share על סרטון",
      'בחר "VerifAI" מרשימת השיתוף',
      "התוצאה מופיעה תוך 2-3 שניות",
    ],
    androidSteps: [
      "פתח TikTok — כפתור 🔍 מופיע על המסך",
      "גלול לסרטון → הכפתור מזהה ולוחץ Share לבד",
      "תוצאה מופיעה מעל TikTok תוך 3-5 שניות",
    ],
    checkBtn: "🔍  בדוק קישור מה-Clipboard",
    analyzing: "⏳  מנתח...",
    history: "היסטוריה",
    clearAll: "נקה הכל",
    copyFirst: "העתק קישור קודם",
    copyHint: "ב-TikTok: לחץ Share ← Copy Link ← חזור לכאן",
    understood: "הבנתי",
    analyzeUrl: "לנתח את הקישור?",
    analyze: "נתח",
    cancel: "ביטול",
    error: "שגיאה",
    connError: "בעיית חיבור",
    clipboardError: "לא ניתן לקרוא clipboard",
    scanning: "⏳ סורק...",
    statAI: "🤖 AI",
    statEdited: "✏️ נערך",
    statReal: "✅ אמיתי",
    confidence: "ביטחון",
    accessBtn: "⚙️ הפעל זיהוי אוטומטי בהגדרות ← נגישות ← VerifAI",
    downloadText: "📲 הורד VerifAI לטלפון אחר",
    premiumBannerTitle: "👑 VerifAI Pro",
    premiumBannerSub: "סריקה אוטומטית · ללא הגבלה · 7 ימים חינם",
  },
  en: {
    poweredBy: "POWERED BY AI",
    noVideos: "No videos analyzed yet",
    noVideosHint: {
      android: "Use the floating 🔍 button while scrolling TikTok",
      ios: "Share a video from TikTok to get started",
    },
    headerSub: {
      android: "Floating 🔍 button appears over any app — detect AI videos in seconds",
      ios: "Share a video from TikTok or Instagram for instant detection",
    },
    overlayCard: "Auto-floating button",
    overlaySub: "Detects videos automatically while scrolling",
    iosCard: "📱 How to use on iPhone",
    iosSteps: [
      "Open TikTok, Instagram or YouTube",
      "Tap Share on any video",
      'Select "VerifAI" from the share sheet',
      "Result appears in 2-3 seconds",
    ],
    androidSteps: [
      "Open TikTok — 🔍 button appears on screen",
      "Scroll to a video → button auto-detects and shares",
      "Result appears over TikTok in 3-5 seconds",
    ],
    checkBtn: "🔍  Check link from Clipboard",
    analyzing: "⏳  Analyzing...",
    history: "History",
    clearAll: "Clear all",
    copyFirst: "Copy a link first",
    copyHint: "In TikTok: tap Share → Copy Link → come back here",
    understood: "Got it",
    analyzeUrl: "Analyze this URL?",
    analyze: "Analyze",
    cancel: "Cancel",
    error: "Error",
    connError: "Connection error",
    clipboardError: "Could not read clipboard",
    scanning: "⏳ Scanning...",
    statAI: "🤖 AI",
    statEdited: "✏️ Edited",
    statReal: "✅ Real",
    confidence: "confidence",
    accessBtn: "⚙️ Enable auto-detection in Settings → Accessibility → VerifAI",
    downloadText: "📲 Download VerifAI on another phone",
    premiumBannerTitle: "👑 VerifAI Pro",
    premiumBannerSub: "Auto-scan · Unlimited · 7 days free",
  },
} as const;
import * as SecureStore from "expo-secure-store";
import * as Clipboard from "expo-clipboard";
import { useOverlay } from "./hooks/useOverlay";
import { detectVideoUrl, DetectionResult } from "./services/detector";
import { OnboardingScreen } from "./components/OnboardingScreen";

const { width } = Dimensions.get("window");
const API = "https://ai-video-detector-production-a305.up.railway.app";
const DOWNLOAD_URL = "https://expo.dev/artifacts/eas/8g8dvWcl6JRyVgbOFgE_x_D0KyO2Fh9X9M-QEFRJGA0.apk";
const PREMIUM_URL = "https://web-zeta-ecru-80.vercel.app/dashboard";

const VIDEO_URL_PATTERNS = [
  /tiktok\.com/, /vm\.tiktok\.com/,
  /instagram\.com/, /facebook\.com/, /fb\.watch\//,
  /youtube\.com/, /youtu\.be\//,
  /twitter\.com/, /x\.com/,
  /reddit\.com/, /v\.redd\.it\//,
  /snapchat\.com/, /pinterest\.com\/pin/,
  /twitch\.tv/, /clips\.twitch\.tv/,
  /vimeo\.com/, /dailymotion\.com/,
  /streamable\.com/, /triller\.co/,
  /likee\.video/, /kwai\.com/,
  /douyin\.com/, /bilibili\.com/,
];
const isVideoUrl = (url: string) => VIDEO_URL_PATTERNS.some((p) => p.test(url));

// ─── Premium Modal ────────────────────────────────────────────────────────────
function PremiumModal({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const scaleAnim = useRef(new Animated.Value(0.85)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(scaleAnim, { toValue: 1, useNativeDriver: true, tension: 80, friction: 8 }),
        Animated.timing(opacityAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
      ]).start();
    } else {
      scaleAnim.setValue(0.85);
      opacityAnim.setValue(0);
    }
  }, [visible]);

  const FEATURES = [
    { icon: "⚡", title: "זיהוי מיידי", desc: "תוצאה תוך שנייה אחת" },
    { icon: "🔁", title: "סריקה אוטומטית", desc: "כל סרטון נסרק לבד בזמן גלילה" },
    { icon: "📊", title: "דו\"ח מפורט", desc: "כלי AI, ביטחון, שיטת זיהוי" },
    { icon: "♾️", title: "ללא הגבלה", desc: "סריקות בלתי מוגבלות ביום" },
    { icon: "🛡️", title: "גישה מוקדמת", desc: "פיצ'רים חדשים ראשון" },
  ];

  return (
    <Modal transparent visible={visible} animationType="none" onRequestClose={onClose}>
      <View style={pm.backdrop}>
        <Animated.View style={[pm.sheet, { transform: [{ scale: scaleAnim }], opacity: opacityAnim }]}>
          {/* Gradient header */}
          <View style={pm.header}>
            <View style={pm.crownWrap}>
              <Text style={pm.crown}>👑</Text>
            </View>
            <Text style={pm.headerTitle}>VerifAI Pro</Text>
            <Text style={pm.headerSub}>זהה תוכן AI מזויף. בכל מקום. אוטומטית.</Text>
          </View>

          {/* Features */}
          <View style={pm.features}>
            {FEATURES.map((f, i) => (
              <View key={i} style={pm.featureRow}>
                <View style={pm.featureIcon}>
                  <Text style={{ fontSize: 18 }}>{f.icon}</Text>
                </View>
                <View style={pm.featureText}>
                  <Text style={pm.featureTitle}>{f.title}</Text>
                  <Text style={pm.featureDesc}>{f.desc}</Text>
                </View>
                <Text style={pm.checkmark}>✓</Text>
              </View>
            ))}
          </View>

          {/* Price */}
          <View style={pm.priceRow}>
            <View>
              <Text style={pm.priceSub}>רק</Text>
              <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 4 }}>
                <Text style={pm.price}>₪19</Text>
                <Text style={pm.pricePer}>/חודש</Text>
              </View>
            </View>
            <View style={pm.badge}>
              <Text style={pm.badgeText}>7 ימים חינם</Text>
            </View>
          </View>

          {/* CTA */}
          <TouchableOpacity style={pm.cta} activeOpacity={0.85} onPress={() => { onClose(); Linking.openURL(PREMIUM_URL); }}>
            <Text style={pm.ctaText}>התחל ניסיון חינם</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={onClose} style={pm.skip}>
            <Text style={pm.skipText}>אולי מאוחר יותר</Text>
          </TouchableOpacity>

          <Text style={pm.terms}>ביטול בכל עת · ללא התחייבות</Text>
        </Animated.View>
      </View>
    </Modal>
  );
}

// ─── Result Banner ────────────────────────────────────────────────────────────
function getVerdictStyle(result: DetectionResult) {
  const v = result.verdict ?? (result.is_ai_generated ? "ai_generated" : "real");
  if (v === "ai_generated") return {
    color: "#ef4444", bg: "#160404",
    label: "🤖  AI GENERATED",
    title: result.ai_tool_detected ? `Made with ${result.ai_tool_detected}` : "AI-Generated Video",
  };
  if (v === "ai_edited") return {
    color: "#a855f7", bg: "#0e0516",
    label: "✏️  נערך עם AI",
    title: result.edit_tool_detected ? `סרטון אמיתי — נערך עם ${result.edit_tool_detected}` : "סרטון אמיתי שנערך בעזרת AI",
  };
  return {
    color: "#22c55e", bg: "#041606",
    label: "✅  AUTHENTIC",
    title: "Real Footage",
  };
}

function ResultBanner({ result, onDismiss, lang = "he" as Lang }: { result: DetectionResult; onDismiss: () => void; lang?: Lang }) {
  const t = T[lang];
  const slideY = useRef(new Animated.Value(-160)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideY, { toValue: 0, useNativeDriver: true, tension: 70, friction: 10 }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
    const t = setTimeout(onDismiss, 8000);
    return () => clearTimeout(t);
  }, []);

  const { color, bg, label, title } = getVerdictStyle(result);
  const pct = Math.round(result.confidence * 100);

  return (
    <Animated.View style={[styles.banner, { backgroundColor: bg, borderColor: color + "55", transform: [{ translateY: slideY }], opacity }]}>
      <View style={[styles.bannerBar, { backgroundColor: color }]} />
      <View style={styles.bannerBody}>
        <View style={styles.bannerLeft}>
          <View style={[styles.bannerBadge, { backgroundColor: color + "18" }]}>
            <View style={[styles.bannerDot, { backgroundColor: color }]} />
            <Text style={[styles.bannerBadgeText, { color }]}>{label}</Text>
          </View>
          <Text style={styles.bannerTitle}>{title}</Text>
          <Text style={styles.bannerMethod} numberOfLines={1}>{result.detection_method}</Text>
        </View>
        <View style={[styles.bannerCircle, { borderColor: color }]}>
          <Text style={[styles.bannerPct, { color }]}>{pct}%</Text>
          <Text style={styles.bannerConf}>{t.confidence}</Text>
        </View>
      </View>
      <TouchableOpacity style={styles.bannerClose} onPress={onDismiss}>
        <Text style={styles.bannerCloseText}>✕</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

// ─── History Row ──────────────────────────────────────────────────────────────
type HistoryItem = DetectionResult & { timestamp: string; url: string };

function HistoryRow({ item, onPress }: { item: HistoryItem; onPress: () => void }) {
  const { color, label, title } = getVerdictStyle(item);
  return (
    <TouchableOpacity style={styles.historyRow} onPress={onPress} activeOpacity={0.7}>
      <View style={[styles.historyBar, { backgroundColor: color }]} />
      <View style={styles.historyInfo}>
        <Text style={styles.historyTitle}>{title}</Text>
        <Text style={[styles.historyUrl, { color: color + "99" }]} numberOfLines={1}>{label}</Text>
        <Text style={styles.historyUrl} numberOfLines={1}>{item.url}</Text>
      </View>
      <View style={[styles.historyPctWrap, { borderColor: color + "66" }]}>
        <Text style={[styles.historyPct, { color }]}>{Math.round(item.confidence * 100)}%</Text>
      </View>
    </TouchableOpacity>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
function AppInner() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showPremium, setShowPremium] = useState(false);
  const [scansToday, setScansToday] = useState(0);
  const [lang, setLang] = useState<Lang>("he");
  const t = T[lang];
  const lastChecked = useRef<string>("");

  const { overlayActive, startOverlay, stopOverlay } = useOverlay();

  // Auto-start overlay on Android
  useEffect(() => {
    if (Platform.OS === "android") startOverlay();
  }, []);

  // Show premium popup: first time after 3 scans, then every 5 scans
  useEffect(() => {
    if (scansToday === 3 || (scansToday > 3 && scansToday % 5 === 0)) {
      const t = setTimeout(() => setShowPremium(true), 1500);
      return () => clearTimeout(t);
    }
  }, [scansToday]);

  // Also show premium popup after 90 seconds idle
  useEffect(() => {
    const t = setTimeout(() => {
      if (!loading && history.length > 0) setShowPremium(true);
    }, 90000);
    return () => clearTimeout(t);
  }, []);

  // Clipboard auto-detect when app comes foreground
  useEffect(() => {
    const { remove } = require("react-native").AppState.addEventListener("change", async (state: string) => {
      if (state !== "active") return;
      try {
        const text = await Clipboard.getStringAsync();
        if (text && text !== lastChecked.current && isVideoUrl(text)) {
          lastChecked.current = text;
          detect(text);
        }
      } catch {}
    });
    return remove;
  }, []);

  const LOADING_ID = "__loading__";

  const detect = useCallback(async (url: string) => {
    setLoading(true);
    setResult(null);
    Vibration.vibrate(30);
    // Add loading placeholder at the TOP of the list immediately
    const loadingItem: HistoryItem = {
      is_ai_generated: false,
      verdict: "real",
      confidence: 0,
      ai_tool_detected: null,
      edit_tool_detected: null,
      detection_method: "",
      timestamp: new Date().toLocaleTimeString("he-IL"),
      url,
      loading: true,
    } as any;
    setHistory((prev) => [loadingItem, ...prev.slice(0, 49)]);
    try {
      const data = await detectVideoUrl(url);
      const item: HistoryItem = { ...data, timestamp: new Date().toLocaleTimeString("he-IL"), url };
      setResult(data);
      // Replace the loading placeholder with the real result
      setHistory((prev) => [item, ...prev.filter((h: any) => !h.loading).slice(0, 49)]);
      setScansToday((n) => n + 1);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch (e: unknown) {
      setHistory((prev) => prev.filter((h: any) => !h.loading));
      Alert.alert(t.error, e instanceof Error ? e.message : t.connError);
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle incoming URLs — deep links, shared links, ACTION_VIEW intents
  const handleIncomingUrl = useCallback((url: string | null) => {
    if (!url) return;
    if (url.startsWith("verifai://")) {
      const match = url.match(/[?&]url=([^&]+)/);
      if (match) {
        const videoUrl = decodeURIComponent(match[1]);
        if (isVideoUrl(videoUrl)) detect(videoUrl);
        return;
      }
    }
    if (isVideoUrl(url)) detect(url);
  }, [detect]);

  useEffect(() => {
    Linking.getInitialURL().then(handleIncomingUrl).catch(() => {});
    const sub = Linking.addEventListener("url", ({ url }) => handleIncomingUrl(url));
    return () => sub.remove();
  }, [handleIncomingUrl]);

  const onManualCheck = useCallback(async () => {
    try {
      const text = await Clipboard.getStringAsync();
      if (!text?.startsWith("http")) {
        Alert.alert(t.copyFirst, t.copyHint, [{ text: t.understood }]);
        return;
      }
      if (!isVideoUrl(text)) {
        Alert.alert(t.analyzeUrl, text.slice(0, 100), [
          { text: t.cancel, style: "cancel" },
          { text: t.analyze, onPress: () => detect(text) },
        ]);
        return;
      }
      detect(text);
    } catch {
      Alert.alert(t.error, t.clipboardError);
    }
  }, [detect, t]);

  const aiCount = history.filter((h) => (h as any).verdict === "ai_generated").length;
  const editedCount = history.filter((h) => (h as any).verdict === "ai_edited").length;
  const realCount = history.filter((h) => (h as any).verdict === "real").length;

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor="#06060f" />

      {result && <ResultBanner result={result} onDismiss={() => setResult(null)} lang={lang} />}
      <PremiumModal visible={showPremium} onClose={() => setShowPremium(false)} />

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

        {/* ── Header ─────────────────────────────────────────────── */}
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <View>
              <Text style={styles.headerEyebrow}>{t.poweredBy}</Text>
              <Text style={styles.headerTitle}>VerifAI</Text>
            </View>
            <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
              <TouchableOpacity
                style={styles.langBtn}
                onPress={() => setLang(l => l === "he" ? "en" : "he")}
              >
                <Text style={styles.langBtnText}>{lang === "he" ? "EN" : "עב"}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.proBtn} onPress={() => setShowPremium(true)}>
                <Text style={styles.proBtnText}>👑 Pro</Text>
              </TouchableOpacity>
            </View>
          </View>
          <Text style={styles.headerSub}>
            {Platform.OS === "android" ? t.headerSub.android : t.headerSub.ios}
          </Text>

          {/* Stats row */}
          {history.length > 0 && (
            <View style={styles.statsRow}>
              <View style={[styles.statBox, { borderColor: "#ef444433" }]}>
                <Text style={[styles.statNum, { color: "#ef4444" }]}>{aiCount}</Text>
                <Text style={styles.statLabel}>{t.statAI}</Text>
              </View>
              <View style={[styles.statBox, { borderColor: "#a855f733" }]}>
                <Text style={[styles.statNum, { color: "#a855f7" }]}>{editedCount}</Text>
                <Text style={styles.statLabel}>{t.statEdited}</Text>
              </View>
              <View style={[styles.statBox, { borderColor: "#22c55e33" }]}>
                <Text style={[styles.statNum, { color: "#22c55e" }]}>{realCount}</Text>
                <Text style={styles.statLabel}>{t.statReal}</Text>
              </View>
            </View>
          )}
        </View>

        {/* ── Android Overlay Card ────────────────────────────────── */}
        {Platform.OS === "android" && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardIcon}>🔍</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{t.overlayCard}</Text>
                <Text style={styles.cardSub}>{t.overlaySub}</Text>
              </View>
              <Switch
                value={overlayActive}
                onValueChange={(v) => (v ? startOverlay() : stopOverlay())}
                trackColor={{ false: "#1a1a2e", true: "#4338ca" }}
                thumbColor={overlayActive ? "#6366f1" : "#374151"}
              />
            </View>

            {overlayActive && (
              <View style={styles.stepsWrap}>
                {t.androidSteps.map((s, i) => (
                  <View key={i} style={styles.stepRow}>
                    <View style={[styles.stepNum, { backgroundColor: "#6366f1" }]}><Text style={styles.stepNumText}>{i + 1}</Text></View>
                    <Text style={styles.stepText}>{s}</Text>
                  </View>
                ))}
                <TouchableOpacity style={styles.accessBtn} onPress={() => Linking.openSettings()}>
                  <Text style={styles.accessBtnText}>{t.accessBtn}</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* ── iOS Card ─────────────────────────────────────────────── */}
        {Platform.OS === "ios" && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t.iosCard}</Text>
            <View style={styles.stepsWrap}>
              {t.iosSteps.map((s, i) => (
                <View key={i} style={styles.stepRow}>
                  <View style={[styles.stepNum, { backgroundColor: "#6366f1" }]}><Text style={styles.stepNumText}>{i + 1}</Text></View>
                  <Text style={styles.stepText}>{s}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* ── Manual Check Button ──────────────────────────────────── */}
        <TouchableOpacity
          style={[styles.checkBtn, loading && styles.checkBtnLoading]}
          onPress={onManualCheck}
          disabled={loading}
          activeOpacity={0.85}
        >
          {loading ? (
            <View style={styles.checkBtnInner}>
              <Text style={styles.checkBtnText}>{t.analyzing}</Text>
              <View style={styles.loadingBar}>
                <Animated.View style={styles.loadingFill} />
              </View>
            </View>
          ) : (
            <Text style={styles.checkBtnText}>{t.checkBtn}</Text>
          )}
        </TouchableOpacity>

        {/* ── Premium Banner ───────────────────────────────────────── */}
        <TouchableOpacity style={styles.premiumBanner} onPress={() => setShowPremium(true)} activeOpacity={0.85}>
          <View>
            <Text style={styles.premiumBannerTitle}>{t.premiumBannerTitle}</Text>
            <Text style={styles.premiumBannerSub}>{t.premiumBannerSub}</Text>
          </View>
          <View style={styles.premiumArrow}>
            <Text style={{ color: "#fff", fontSize: 14 }}>←</Text>
          </View>
        </TouchableOpacity>

        {/* ── History ──────────────────────────────────────────────── */}
        {history.length > 0 && (
          <View style={styles.section}>
            <View style={styles.sectionRow}>
              <Text style={styles.sectionTitle}>{t.history}</Text>
              <TouchableOpacity onPress={() => setHistory([])}>
                <Text style={styles.clearBtn}>{t.clearAll}</Text>
              </TouchableOpacity>
            </View>
            {history.map((item, i) =>
              (item as any).loading ? (
                <View key="loading" style={[styles.historyRow, { padding: 14, gap: 10 }]}>
                  <View style={[styles.historyBar, { backgroundColor: "#6366f1" }]} />
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={[styles.historyTitle, { color: "#6366f1" }]}>{t.scanning}</Text>
                    <Text style={styles.historyUrl} numberOfLines={1}>{item.url}</Text>
                  </View>
                </View>
              ) : (
                <HistoryRow key={i} item={item} onPress={() => setResult(item)} />
              )
            )}
          </View>
        )}

        {history.length === 0 && (
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>🎬</Text>
            <Text style={styles.emptyTitle}>{t.noVideos}</Text>
            <Text style={styles.emptyHint}>
              {Platform.OS === "android" ? t.noVideosHint.android : t.noVideosHint.ios}
            </Text>
          </View>
        )}

        {/* Download link */}
        <TouchableOpacity onPress={() => Linking.openURL(DOWNLOAD_URL)} style={styles.downloadLink}>
          <Text style={styles.downloadText}>{t.downloadText}</Text>
        </TouchableOpacity>

      </ScrollView>
    </SafeAreaView>
  );
}

export default function App() {
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    SecureStore.getItemAsync("onboarded").then((v) => setOnboarded(v === "1")).catch(() => setOnboarded(false));
  }, []);

  const finishOnboarding = async () => {
    await SecureStore.setItemAsync("onboarded", "1").catch(() => {});
    setOnboarded(true);
  };

  if (onboarded === null) return null; // loading

  if (!onboarded) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: "#06060f" }}>
        <StatusBar barStyle="light-content" backgroundColor="#06060f" />
        <OnboardingScreen onDone={finishOnboarding} />
      </SafeAreaView>
    );
  }

  return <AppInner />;
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#06060f" },
  scroll: { padding: 18, paddingBottom: 60, gap: 14 },

  // Banner
  banner: {
    position: "absolute", top: 52, left: 10, right: 10, zIndex: 9999,
    borderRadius: 20, borderWidth: 1, overflow: "hidden",
    shadowColor: "#000", shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.7, shadowRadius: 24, elevation: 24,
  },
  bannerBar: { height: 3 },
  bannerBody: { flexDirection: "row", alignItems: "center", padding: 16, gap: 12 },
  bannerLeft: { flex: 1, gap: 6 },
  bannerBadge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", paddingHorizontal: 9, paddingVertical: 3, borderRadius: 20 },
  bannerDot: { width: 5, height: 5, borderRadius: 3 },
  bannerBadgeText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.8 },
  bannerTitle: { color: "#fff", fontSize: 16, fontWeight: "700" },
  bannerMethod: { color: "#555", fontSize: 11 },
  bannerCircle: { width: 66, height: 66, borderRadius: 33, borderWidth: 2.5, alignItems: "center", justifyContent: "center" },
  bannerPct: { fontSize: 18, fontWeight: "800" },
  bannerConf: { color: "#555", fontSize: 8 },
  bannerClose: { position: "absolute", top: 10, right: 12, padding: 6 },
  bannerCloseText: { color: "#555", fontSize: 14 },

  // Header
  header: { paddingTop: 4, gap: 10 },
  headerTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  headerEyebrow: { color: "#6366f1", fontSize: 10, fontWeight: "800", letterSpacing: 3 },
  headerTitle: { color: "#fff", fontSize: 42, fontWeight: "900", letterSpacing: -2, lineHeight: 44 },
  headerSub: { color: "#4b5563", fontSize: 13, lineHeight: 19 },
  langBtn: { backgroundColor: "#0e0e1a", borderRadius: 16, paddingHorizontal: 11, paddingVertical: 7, borderWidth: 1, borderColor: "#ffffff15" },
  langBtnText: { color: "#6b7280", fontSize: 12, fontWeight: "700" },
  proBtn: { backgroundColor: "#1a1040", borderRadius: 20, paddingHorizontal: 14, paddingVertical: 7, borderWidth: 1, borderColor: "#6366f133" },
  proBtnText: { color: "#a78bfa", fontSize: 13, fontWeight: "700" },

  // Stats
  statsRow: { flexDirection: "row", gap: 10, marginTop: 4 },
  statBox: { flex: 1, backgroundColor: "#0d0d1a", borderRadius: 14, padding: 12, alignItems: "center", borderWidth: 1, borderColor: "#ffffff0a" },
  statNum: { color: "#fff", fontSize: 22, fontWeight: "800" },
  statLabel: { color: "#444", fontSize: 10, fontWeight: "600", marginTop: 2 },

  // Card
  card: { backgroundColor: "#0c0c1a", borderRadius: 20, padding: 18, borderWidth: 1, borderColor: "#ffffff08", gap: 14 },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: 12 },
  cardIcon: { fontSize: 26 },
  cardTitle: { color: "#e5e7eb", fontWeight: "700", fontSize: 15 },
  cardSub: { color: "#4b5563", fontSize: 12, marginTop: 2 },

  // Steps
  stepsWrap: { gap: 10 },
  stepRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  stepNum: { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center" },
  stepNumText: { color: "#fff", fontSize: 11, fontWeight: "800" },
  stepText: { color: "#9ca3af", fontSize: 13, flex: 1, lineHeight: 18 },

  accessBtn: { backgroundColor: "#11113a", borderRadius: 12, padding: 12, marginTop: 4, borderWidth: 1, borderColor: "#6366f122" },
  accessBtnText: { color: "#6366f1", fontSize: 12, textAlign: "center", lineHeight: 18 },

  // Check button
  checkBtn: {
    backgroundColor: "#4f46e5", borderRadius: 18, padding: 18, alignItems: "center",
    shadowColor: "#4f46e5", shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.5, shadowRadius: 16, elevation: 10,
  },
  checkBtnLoading: { backgroundColor: "#1f1f35" },
  checkBtnInner: { alignItems: "center", gap: 8, width: "100%" },
  checkBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  loadingBar: { height: 2, width: "60%", backgroundColor: "#ffffff22", borderRadius: 1 },
  loadingFill: { height: 2, width: "40%", backgroundColor: "#6366f1", borderRadius: 1 },

  // Premium banner
  premiumBanner: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    borderRadius: 18, padding: 16,
    backgroundColor: "#120a2e",
    borderWidth: 1, borderColor: "#7c3aed55",
  },
  premiumBannerTitle: { color: "#c4b5fd", fontSize: 15, fontWeight: "800" },
  premiumBannerSub: { color: "#6d28d9", fontSize: 12, marginTop: 3 },
  premiumArrow: { backgroundColor: "#7c3aed", borderRadius: 12, width: 32, height: 32, alignItems: "center", justifyContent: "center" },

  // Section
  section: { gap: 10 },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sectionTitle: { color: "#374151", fontSize: 10, fontWeight: "700", letterSpacing: 1.5 },
  clearBtn: { color: "#374151", fontSize: 12 },

  // History
  historyRow: { flexDirection: "row", alignItems: "center", backgroundColor: "#0c0c1a", borderRadius: 16, overflow: "hidden", borderWidth: 1, borderColor: "#ffffff07" },
  historyBar: { width: 3, alignSelf: "stretch" },
  historyInfo: { flex: 1, gap: 3, padding: 14 },
  historyTitle: { color: "#d1d5db", fontSize: 13, fontWeight: "600" },
  historyUrl: { color: "#374151", fontSize: 10 },
  historyTime: { color: "#2d3748", fontSize: 10 },
  historyPctWrap: { marginRight: 14, width: 50, height: 50, borderRadius: 25, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  historyPct: { fontSize: 14, fontWeight: "800" },

  // Empty
  empty: { alignItems: "center", paddingVertical: 50, gap: 10 },
  emptyIcon: { fontSize: 56 },
  emptyTitle: { color: "#374151", fontSize: 16, fontWeight: "700" },
  emptyHint: { color: "#1f2937", fontSize: 13, textAlign: "center", lineHeight: 19, paddingHorizontal: 20 },

  // Download
  downloadLink: { alignItems: "center", paddingVertical: 12 },
  downloadText: { color: "#374151", fontSize: 12 },
});

// ─── Premium Modal Styles ─────────────────────────────────────────────────────
const pm = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: "#0d0d1e", borderTopLeftRadius: 32, borderTopRightRadius: 32,
    paddingBottom: 40, overflow: "hidden",
    borderWidth: 1, borderColor: "#ffffff0a",
  },
  header: {
    backgroundColor: "#120a2e", padding: 28, alignItems: "center", gap: 8,
  },
  crownWrap: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#7c3aed33", alignItems: "center", justifyContent: "center", marginBottom: 4 },
  crown: { fontSize: 32 },
  headerTitle: { color: "#fff", fontSize: 26, fontWeight: "900", letterSpacing: -0.5 },
  headerSub: { color: "#7c3aed", fontSize: 13, textAlign: "center", lineHeight: 18 },

  features: { padding: 22, gap: 16 },
  featureRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  featureIcon: { width: 42, height: 42, borderRadius: 12, backgroundColor: "#1a0a3d", alignItems: "center", justifyContent: "center" },
  featureText: { flex: 1 },
  featureTitle: { color: "#e5e7eb", fontSize: 14, fontWeight: "700" },
  featureDesc: { color: "#6b7280", fontSize: 12, marginTop: 1 },
  checkmark: { color: "#7c3aed", fontSize: 18, fontWeight: "800" },

  priceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 22, marginBottom: 18 },
  priceSub: { color: "#6b7280", fontSize: 11 },
  price: { color: "#fff", fontSize: 36, fontWeight: "900" },
  pricePer: { color: "#6b7280", fontSize: 14, marginBottom: 8 },
  badge: { backgroundColor: "#7c3aed22", borderRadius: 12, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderColor: "#7c3aed55" },
  badgeText: { color: "#a78bfa", fontSize: 13, fontWeight: "700" },

  cta: {
    marginHorizontal: 20, borderRadius: 18, padding: 18, alignItems: "center",
    backgroundColor: "#7c3aed",
    shadowColor: "#7c3aed", shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.5, shadowRadius: 16, elevation: 10,
  },
  ctaText: { color: "#fff", fontSize: 17, fontWeight: "800" },
  skip: { alignItems: "center", paddingVertical: 16 },
  skipText: { color: "#374151", fontSize: 14 },
  terms: { color: "#1f2937", fontSize: 11, textAlign: "center" },
});
