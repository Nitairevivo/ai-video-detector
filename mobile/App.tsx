import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  View, Text, StyleSheet, Animated, TouchableOpacity, ActivityIndicator,
  SafeAreaView, StatusBar, ScrollView, Alert, Vibration, Easing,
  Platform, Switch, Modal, Dimensions, Linking, AppState, TextInput,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system";
import { LinearGradient } from "expo-linear-gradient";
import { useOverlay, OverlayStatus } from "./hooks/useOverlay";
import { detectVideoUrl, DetectionResult } from "./services/detector";
import { CHANGELOG, CHANGELOG_VERSION } from "./changelog";
import { SelfCheck } from "./SelfCheck";

const { width } = Dimensions.get("window");
const API = "https://ai-video-detector-production-a305.up.railway.app";
const DOWNLOAD_URL = "https://expo.dev/artifacts/eas/oUG3Z0GPBAub2rp4xlimg7lDoai3D16thT3n-m3Uhow.apk";
const PREMIUM_URL = "https://web-zeta-ecru-80.vercel.app/dashboard";

const APP_VERSION = "1.6.0";

// The signature bold brand gradient — violet → magenta → cyan.
const GRAD = ["#7c3aed", "#d946ef", "#22e3ee"] as const;
const GRAD_START = { x: 0, y: 0 };
const GRAD_END = { x: 1, y: 1 };
const JS_ERROR_KEY = "verifai_last_js_error";
const LANG_KEY = "verifai_lang";
const HISTORY_FILE = FileSystem.documentDirectory + "verifai_history.json";

// ─── Design tokens ────────────────────────────────────────────────────────────
const C = {
  bg: "#070316",
  card: "#0e0a24",
  card2: "#17103a",
  border: "#ffffff14",
  text: "#f4f2ff",
  sub: "#a29dc4",
  faint: "#6b6690",
  primary: "#a066ff",      // bright signal violet
  primaryDeep: "#6d28ff",  // electric indigo
  magenta: "#ff3ec9",      // hot magenta accent
  cyan: "#22e3ee",         // cyan spark
  ai: "#ff3d6e",
  edited: "#c084fc",
  real: "#2ee6a6",
  gold: "#fbbf24",
  violet: "#b061ff",
};

// ─── i18n — Hebrew / English ──────────────────────────────────────────────────
type Lang = "he" | "en";

const T = {
  he: {
    tagline: "גלה מה אמיתי. תוך שניות.",
    scanBtn: "בדוק סרטון",
    scanHint: "מעתיק קישור? פשוט חזור לכאן — נזהה אותו לבד",
    detectTitle: "בדוק סרטון או תמונה",
    detectSub: "הדבק קישור מטיקטוק / יוטיוב / אינסטגרם / X",
    pastePlaceholder: "הדבק כאן קישור…",
    pasteBtn: "הדבק",
    detectNow: "בדוק עכשיו",
    detectTip: "טיפ: אפשר גם לשתף סרטון או תמונה מכל אפליקציה אל VerifAI",
    invalidLink: "הדבק קישור תקין שמתחיל ב-http",
    howKnowTitle: "איך VerifAI יודע?",
    howKnowRows: [
      ["🔏", "קורא את הקוד של הקובץ — אישורי C2PA וחתימות של כלי-AI (Sora, Veo, Midjourney…)"],
      ["🏷️", "קורא את תוויות ה-AI של הפלטפורמות — TikTok, YouTube, Instagram, X"],
      ["👁️", "ואם צריך — ניתוח חזותי מכויל, כדי לא לטעות"],
    ],
    provIptc: "🏷 תקן IPTC מצהיר: מדיה שנוצרה ב-AI",
    provCamera: "📷 תקן IPTC מצהיר: צולם במצלמה",
    fastMode: "⚡ זוהה מהקוד — מיידי",
    analyzing: "מנתח…",
    stages: ["מאתר את הסרטון…", "מוריד נתונים…", "מנתח פריימים…", "מצליב ממצאים…"],
    statusTitle: "מרכז בקרה",
    statusOverlayPerm: "הרשאת תצוגה מעל אפליקציות",
    statusAccess: "זיהוי אוטומטי (נגישות)",
    statusService: "כפתור צף פעיל",
    statusFix: "תקן",
    statusOn: "פעיל",
    statusOff: "כבוי",
    statusAllGood: "הכל מוגדר — הכפתור יופיע בתוך TikTok, Instagram ו-YouTube",
    howTitle: "איך זה עובד?",
    howSteps: [
      "פתח TikTok / Instagram / YouTube — כפתור VerifAI יופיע בצד",
      "לחץ עליו — הסרטון שעל המסך ייבדק אוטומטית",
      "התוצאה תופיע מעל הסרטון תוך כמה שניות",
    ],
    howIos: [
      "פתח TikTok, Instagram או YouTube",
      "לחץ Share על סרטון ובחר VerifAI",
      "התוצאה מופיעה תוך שניות",
    ],
    history: "בדיקות אחרונות",
    clearAll: "נקה",
    empty: "עדיין לא נבדקו סרטונים",
    emptyHint: {
      android: "הפעל את הכפתור הצף למעלה, או העתק קישור לסרטון ולחץ על הכפתור הגדול",
      ios: "שתף סרטון מ-TikTok אל VerifAI, או העתק קישור ולחץ על הכפתור הגדול",
    },
    statAI: "AI",
    statEdited: "נערך",
    statReal: "אמיתי",
    confidence: "רמת ביטחון",
    verdictAI: "נוצר ב-AI",
    verdictEdited: "נערך עם AI",
    verdictReal: "צילום אמיתי",
    verdictUnknown: "לא חד-משמעי",
    madeWith: "נוצר עם",
    editedWith: "נערך עם",
    method: "שיטת זיהוי",
    layers: "שכבות ניתוח",
    provC2paAi: "🔏 חתימת C2PA: נוצר ב-AI (מאומת)",
    provC2pa: "🔏 נמצאו Content Credentials",
    provStripped: "המטא-דאטה המקורי נמחק ע״י הפלטפורמה",
    meaningAI: "המערכת זיהתה סימנים מובהקים של יצירה מלאכותית. מומלץ לא להסתמך על הסרטון כתיעוד אמיתי.",
    meaningEdited: "הצילום אמיתי, אך עבר עריכה בכלי AI (פילטרים, החלפת פנים או שיפור).",
    meaningReal: "לא נמצאו סימני AI — הסרטון נראה כצילום מצלמה אותנטי.",
    meaningUnknown: "האותות סותרים — נסה לבדוק שוב עם קישור ישיר לסרטון.",
    checkAgain: "בדוק שוב",
    copyResult: "העתק תוצאה",
    copied: "הועתק!",
    close: "סגור",
    scanning: "סורק…",
    copyFirst: "אין קישור בלוח",
    copyHint: "בתוך TikTok: לחץ Share ← Copy Link, ואז חזור לכאן",
    understood: "הבנתי",
    analyzeUrl: "לנתח את הקישור?",
    analyze: "נתח",
    cancel: "ביטול",
    error: "שגיאה",
    connError: "בעיית חיבור — נסה שוב",
    clipboardError: "לא ניתן לקרוא את הלוח",
    premiumBannerTitle: "VerifAI Pro",
    premiumBannerSub: "סריקה אוטומטית · ללא הגבלה · 7 ימים חינם",
    downloadText: "הורד את VerifAI לטלפון נוסף",
    resultFor: "נבדק",
    platformFile: "קובץ וידאו",
  },
  en: {
    tagline: "Know what's real. In seconds.",
    scanBtn: "Check video",
    scanHint: "Copied a link? Just come back here — we'll catch it",
    detectTitle: "Check a video or image",
    detectSub: "Paste a TikTok / YouTube / Instagram / X link",
    pastePlaceholder: "Paste a link here…",
    pasteBtn: "Paste",
    detectNow: "Detect now",
    detectTip: "Tip: you can also Share a video or image from any app to VerifAI",
    invalidLink: "Paste a valid link that starts with http",
    howKnowTitle: "How VerifAI knows",
    howKnowRows: [
      ["🔏", "Reads the file's code — C2PA credentials & AI-tool signatures (Sora, Veo, Midjourney…)"],
      ["🏷️", "Reads the platforms' own AI labels — TikTok, YouTube, Instagram, X"],
      ["👁️", "And when needed, a calibrated visual check — so it doesn't cry wolf"],
    ],
    provIptc: "🏷 IPTC standard declares: AI-generated media",
    provCamera: "📷 IPTC standard declares: camera capture",
    fastMode: "⚡ Read from code — instant",
    analyzing: "Analyzing…",
    stages: ["Locating video…", "Fetching data…", "Analyzing frames…", "Cross-checking…"],
    statusTitle: "Control center",
    statusOverlayPerm: "Display over other apps",
    statusAccess: "Auto-detection (accessibility)",
    statusService: "Floating button",
    statusFix: "Fix",
    statusOn: "On",
    statusOff: "Off",
    statusAllGood: "All set — the button shows up inside TikTok, Instagram & YouTube",
    howTitle: "How it works",
    howSteps: [
      "Open TikTok / Instagram / YouTube — the VerifAI button appears",
      "Tap it — the video on screen gets checked automatically",
      "The verdict pops up over the video within seconds",
    ],
    howIos: [
      "Open TikTok, Instagram or YouTube",
      "Tap Share on a video and pick VerifAI",
      "The verdict appears in seconds",
    ],
    history: "Recent checks",
    clearAll: "Clear",
    empty: "No videos checked yet",
    emptyHint: {
      android: "Turn on the floating button above, or copy a video link and tap the big button",
      ios: "Share a video from TikTok to VerifAI, or copy a link and tap the big button",
    },
    statAI: "AI",
    statEdited: "Edited",
    statReal: "Real",
    confidence: "Confidence",
    verdictAI: "AI Generated",
    verdictEdited: "AI Edited",
    verdictReal: "Authentic footage",
    verdictUnknown: "Inconclusive",
    madeWith: "Made with",
    editedWith: "Edited with",
    method: "Detection method",
    layers: "Analysis layers",
    provC2paAi: "🔏 C2PA signature: AI-generated (verified)",
    provC2pa: "🔏 Content Credentials found",
    provStripped: "Original metadata stripped by the platform",
    meaningAI: "Strong signs of synthetic generation were found. Don't rely on this video as real documentation.",
    meaningEdited: "The footage is real but was edited with AI tools (filters, face swap or enhancement).",
    meaningReal: "No AI fingerprints found — this looks like authentic camera footage.",
    meaningUnknown: "Signals are conflicting — try again with a direct link to the video.",
    checkAgain: "Check again",
    copyResult: "Copy result",
    copied: "Copied!",
    close: "Close",
    scanning: "Scanning…",
    copyFirst: "No link in clipboard",
    copyHint: "In TikTok: tap Share → Copy Link, then come back here",
    understood: "Got it",
    analyzeUrl: "Analyze this URL?",
    analyze: "Analyze",
    cancel: "Cancel",
    error: "Error",
    connError: "Connection problem — try again",
    clipboardError: "Could not read the clipboard",
    premiumBannerTitle: "VerifAI Pro",
    premiumBannerSub: "Auto-scan · Unlimited · 7 days free",
    downloadText: "Get VerifAI on another phone",
    resultFor: "Checked",
    platformFile: "Video file",
  },
} as const;

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
type Strings = (typeof T)[Lang];
const isVideoUrl = (url: string) => VIDEO_URL_PATTERNS.some((p) => p.test(url));

function platformName(url: string, t: Strings): string {
  if (/tiktok/.test(url)) return "TikTok";
  if (/instagram/.test(url)) return "Instagram";
  if (/youtu/.test(url)) return "YouTube";
  if (/facebook|fb\.watch/.test(url)) return "Facebook";
  if (/twitter|x\.com/.test(url)) return "X";
  if (/reddit|redd\.it/.test(url)) return "Reddit";
  if (/snapchat/.test(url)) return "Snapchat";
  if (url.startsWith("http")) return new URL(url).hostname.replace("www.", "");
  return t.platformFile;
}

type Verdict = "ai_generated" | "ai_edited" | "real" | "unknown";
type HistoryItem = DetectionResult & { timestamp: string; url: string; loading?: boolean };

function verdictOf(r: DetectionResult): Verdict {
  return (r.verdict as Verdict) ?? (r.is_ai_generated ? "ai_generated" : "real");
}

function verdictTheme(v: Verdict, t: Strings) {
  switch (v) {
    case "ai_generated": return { color: C.ai, bg: "#1c0710", label: t.verdictAI, emoji: "🤖", meaning: t.meaningAI };
    case "ai_edited": return { color: C.edited, bg: "#150826", label: t.verdictEdited, emoji: "🎭", meaning: t.meaningEdited };
    case "unknown": return { color: C.gold, bg: "#1c1405", label: t.verdictUnknown, emoji: "🤔", meaning: t.meaningUnknown };
    default: return { color: C.real, bg: "#04170f", label: t.verdictReal, emoji: "✅", meaning: t.meaningReal };
  }
}

// ─── Result Sheet (bottom sheet, replaces the old cramped top banner) ─────────
function ResultSheet({ item, onClose, onRecheck, lang }: {
  item: HistoryItem; onClose: () => void; onRecheck: (url: string) => void; lang: Lang;
}) {
  const t = T[lang];
  const rtl = lang === "he";
  const v = verdictOf(item);
  const th = verdictTheme(v, t);
  const pct = Math.round(item.confidence * 100);

  const slide = useRef(new Animated.Value(400)).current;
  const barAnim = useRef(new Animated.Value(0)).current;
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Animated.spring(slide, { toValue: 0, useNativeDriver: true, tension: 60, friction: 11 }).start();
    Animated.timing(barAnim, { toValue: pct, duration: 900, easing: Easing.out(Easing.cubic), useNativeDriver: false }).start();
  }, []);

  const dismiss = () => {
    Animated.timing(slide, { toValue: 500, duration: 200, useNativeDriver: true }).start(onClose);
  };

  const prov = item.explanation?.provenance;
  const provLine = prov?.c2pa_claims_ai ? t.provC2paAi
    : prov?.synthetic_media_marker ? t.provIptc
    : prov?.camera_provenance ? t.provCamera
    : prov?.c2pa_present ? t.provC2pa
    : (prov?.metadata_stripped || prov?.platform_reencoded) ? t.provStripped
    : null;
  const layers = item.explanation?.layer_scores
    ? Object.entries(item.explanation.layer_scores).slice(0, 4) : [];
  const timeline = item.explanation?.frame_timeline;
  const caveat = item.explanation?.caveats?.[0];

  const copyResult = async () => {
    const summary = `VerifAI · ${th.label} (${pct}%)\n${item.url}`;
    try { await Clipboard.setStringAsync(summary); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch {}
  };

  const align = { textAlign: (rtl ? "right" : "left") as "right" | "left" };
  const row = { flexDirection: (rtl ? "row-reverse" : "row") as "row-reverse" | "row" };

  return (
    <Modal transparent visible animationType="none" onRequestClose={dismiss}>
      <TouchableOpacity style={rs.backdrop} activeOpacity={1} onPress={dismiss}>
        <TouchableOpacity activeOpacity={1} onPress={() => {}}>
          <Animated.View style={[rs.sheet, { transform: [{ translateY: slide }] }]}>
            <View style={rs.grabber} />

            {/* Verdict header */}
            <View style={[rs.header, { backgroundColor: th.bg, borderColor: th.color + "44" }]}>
              <Text style={rs.headerEmoji}>{th.emoji}</Text>
              <Text style={[rs.headerLabel, { color: th.color }]}>{th.label}</Text>
              {v === "ai_generated" && item.ai_tool_detected ? (
                <Text style={rs.headerTool}>{t.madeWith} {item.ai_tool_detected}</Text>
              ) : v === "ai_edited" && item.edit_tool_detected ? (
                <Text style={rs.headerTool}>{t.editedWith} {item.edit_tool_detected}</Text>
              ) : null}
              {item.mode === "fast" && <Text style={rs.fastBadge}>{t.fastMode}</Text>}
            </View>

            {/* Confidence */}
            <View style={rs.confWrap}>
              <View style={[rs.confRow, row]}>
                <Text style={[rs.confLabel, align]}>{t.confidence}</Text>
                <Text style={[rs.confPct, { color: th.color }]}>{pct}%</Text>
              </View>
              <View style={rs.confTrack}>
                <Animated.View style={[rs.confFill, {
                  backgroundColor: th.color,
                  width: barAnim.interpolate({ inputRange: [0, 100], outputRange: ["0%", "100%"] }),
                }]} />
              </View>
            </View>

            {/* What it means */}
            <Text style={[rs.meaning, align]}>{th.meaning}</Text>

            {/* Details */}
            <View style={rs.details}>
              {!!item.detection_method && (
                <View style={[rs.detailRow, row]}>
                  <Text style={rs.detailKey}>{t.method}</Text>
                  <Text style={[rs.detailVal, align]} numberOfLines={2}>{item.detection_method}</Text>
                </View>
              )}
              {provLine && (
                <View style={[rs.detailRow, row]}>
                  <Text style={rs.detailKey}>C2PA</Text>
                  <Text style={[rs.detailVal, align]}>{provLine}</Text>
                </View>
              )}
              {layers.length > 0 && (
                <View style={{ gap: 6, marginTop: 4 }}>
                  <Text style={[rs.detailKey, align]}>{t.layers}</Text>
                  {layers.map(([k, val]) => (
                    <View key={k} style={[rs.layerRow, row]}>
                      <Text style={rs.layerName} numberOfLines={1}>{k}</Text>
                      <View style={rs.layerTrack}>
                        <View style={[rs.layerFill, {
                          width: `${Math.round((val as number) * 100)}%`,
                          backgroundColor: (val as number) > 0.5 ? C.ai : C.real,
                        }]} />
                      </View>
                      <Text style={rs.layerPct}>{Math.round((val as number) * 100)}%</Text>
                    </View>
                  ))}
                </View>
              )}
              {timeline && timeline.length >= 2 && (
                // Per-frame suspicion sparkline (green=natural, red=AI-like) —
                // the same forensic signal the web report shows.
                <View style={rs.timeline}>
                  {timeline.map((val, i) => (
                    <View key={i} style={{
                      flex: 1,
                      height: Math.max(2, Math.round(val * 20)),
                      backgroundColor: val >= 0.6 ? C.ai : val <= 0.4 ? C.real : C.gold,
                      borderRadius: 1,
                    }} />
                  ))}
                </View>
              )}
              {!!caveat && <Text style={[rs.caveat, align]} numberOfLines={2}>⚠ {caveat}</Text>}
              <Text style={[rs.urlLine, align]} numberOfLines={1}>
                {t.resultFor} · {platformName(item.url, t)} · {item.timestamp}
              </Text>
            </View>

            {/* Actions */}
            <View style={[rs.actions, row]}>
              <TouchableOpacity style={[rs.actionBtn, rs.actionPrimary]} onPress={() => { dismiss(); onRecheck(item.url); }}>
                <Text style={rs.actionPrimaryText}>{t.checkAgain}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={rs.actionBtn} onPress={copyResult}>
                <Text style={rs.actionText}>{copied ? t.copied : t.copyResult}</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
}

// ─── Premium Modal ────────────────────────────────────────────────────────────
function PremiumModal({ visible, onClose, lang }: { visible: boolean; onClose: () => void; lang: Lang }) {
  const rtl = lang === "he";
  const slide = useRef(new Animated.Value(500)).current;

  useEffect(() => {
    if (visible) {
      slide.setValue(500);
      Animated.spring(slide, { toValue: 0, useNativeDriver: true, tension: 55, friction: 11 }).start();
    }
  }, [visible]);

  const FEATURES = rtl ? [
    { icon: "⚡", title: "זיהוי מיידי", desc: "תוצאה תוך שנייה" },
    { icon: "🔁", title: "סריקה אוטומטית", desc: "כל סרטון נבדק לבד בזמן גלילה" },
    { icon: "📊", title: "דו״ח מפורט", desc: "כלי AI, שכבות ניתוח, חתימות" },
    { icon: "♾️", title: "ללא הגבלה", desc: "בדיקות בלתי מוגבלות" },
  ] : [
    { icon: "⚡", title: "Instant detection", desc: "Results in one second" },
    { icon: "🔁", title: "Auto-scan", desc: "Every video checked while you scroll" },
    { icon: "📊", title: "Full report", desc: "AI tools, analysis layers, signatures" },
    { icon: "♾️", title: "Unlimited", desc: "No daily limits" },
  ];

  const row = { flexDirection: (rtl ? "row-reverse" : "row") as "row-reverse" | "row" };
  const align = { textAlign: (rtl ? "right" : "left") as "right" | "left" };

  return (
    <Modal transparent visible={visible} animationType="none" onRequestClose={onClose}>
      <View style={pm.backdrop}>
        <Animated.View style={[pm.sheet, { transform: [{ translateY: slide }] }]}>
          <View style={pm.header}>
            <View style={pm.crownWrap}><Text style={{ fontSize: 30 }}>👑</Text></View>
            <Text style={pm.headerTitle}>VerifAI Pro</Text>
            <Text style={pm.headerSub}>{rtl ? "זהה תוכן מזויף. בכל מקום. אוטומטית." : "Spot fake content. Everywhere. Automatically."}</Text>
          </View>

          <View style={pm.features}>
            {FEATURES.map((f, i) => (
              <View key={i} style={[pm.featureRow, row]}>
                <View style={pm.featureIcon}><Text style={{ fontSize: 17 }}>{f.icon}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={[pm.featureTitle, align]}>{f.title}</Text>
                  <Text style={[pm.featureDesc, align]}>{f.desc}</Text>
                </View>
                <Text style={pm.checkmark}>✓</Text>
              </View>
            ))}
          </View>

          <View style={[pm.priceRow, row]}>
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "flex-end", gap: 4 }}>
              <Text style={pm.price}>₪19</Text>
              <Text style={pm.pricePer}>/{rtl ? "חודש" : "mo"}</Text>
            </View>
            <View style={pm.badge}><Text style={pm.badgeText}>{rtl ? "7 ימים חינם" : "7 days free"}</Text></View>
          </View>

          <TouchableOpacity style={pm.cta} activeOpacity={0.85} onPress={() => { onClose(); Linking.openURL(PREMIUM_URL); }}>
            <Text style={pm.ctaText}>{rtl ? "התחל ניסיון חינם" : "Start free trial"}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} style={pm.skip}>
            <Text style={pm.skipText}>{rtl ? "אולי מאוחר יותר" : "Maybe later"}</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>
    </Modal>
  );
}

// Google Play variant ships without the accessibility service (Play policy) —
// hide its diagnostics row and don't count it toward "all set".
// Inlined at build time from eas.json profile "play".
const PLAY_BUILD = process.env.EXPO_PUBLIC_PLAY_BUILD === "1";

// ─── Status (diagnostics) card — answers "why isn't the button working?" ──────
function StatusCard({ status, overlayActive, onToggle, lang }: {
  status: OverlayStatus; overlayActive: boolean;
  onToggle: (v: boolean) => void; lang: Lang;
}) {
  const t = T[lang];
  const rtl = lang === "he";
  const row = { flexDirection: (rtl ? "row-reverse" : "row") as "row-reverse" | "row" };
  const align = { textAlign: (rtl ? "right" : "left") as "right" | "left" };
  const { OverlayModule } = require("react-native").NativeModules;

  const allGood = status.overlayPermission && (PLAY_BUILD || status.accessibilityEnabled) && overlayActive;

  const Row = ({ ok, label, onFix }: { ok: boolean; label: string; onFix?: () => void }) => (
    <View style={[st.row, row]}>
      <View style={[st.dot, { backgroundColor: ok ? C.real : C.ai }]} />
      <Text style={[st.rowLabel, align, { flex: 1 }]}>{label}</Text>
      {ok ? (
        <Text style={st.okText}>{t.statusOn} ✓</Text>
      ) : onFix ? (
        <TouchableOpacity style={st.fixBtn} onPress={onFix}>
          <Text style={st.fixText}>{t.statusFix}</Text>
        </TouchableOpacity>
      ) : (
        <Text style={st.offText}>{t.statusOff}</Text>
      )}
    </View>
  );

  return (
    <View style={s.card}>
      <View style={[st.header, row]}>
        <Text style={[s.cardTitle, align]}>{t.statusTitle}</Text>
        <Switch
          value={overlayActive}
          onValueChange={onToggle}
          trackColor={{ false: "#1c1e36", true: C.primaryDeep }}
          thumbColor={overlayActive ? C.primary : "#3a3f58"}
        />
      </View>

      <Row
        ok={status.overlayPermission}
        label={t.statusOverlayPerm}
        onFix={() => OverlayModule?.requestPermission?.()}
      />
      {!PLAY_BUILD && (
        <Row
          ok={status.accessibilityEnabled}
          label={t.statusAccess}
          onFix={() => OverlayModule?.openAccessibilitySettings?.().catch(() => Linking.openSettings())}
        />
      )}
      <Row ok={overlayActive} label={t.statusService} />

      {allGood && <Text style={[st.allGood, align]}>{t.statusAllGood}</Text>}
    </View>
  );
}

// ─── History Row ──────────────────────────────────────────────────────────────
function HistoryRow({ item, onPress, lang }: { item: HistoryItem; onPress: () => void; lang: Lang }) {
  const t = T[lang];
  const rtl = lang === "he";
  const v = verdictOf(item);
  const th = verdictTheme(v, t);
  return (
    <TouchableOpacity
      style={[s.historyRow, { flexDirection: rtl ? "row-reverse" : "row" }]}
      onPress={onPress} activeOpacity={0.7}
    >
      <View style={[s.historyBar, { backgroundColor: th.color }]} />
      <View style={[s.historyInfo, { alignItems: rtl ? "flex-end" : "flex-start" }]}>
        <View style={[s.historyBadge, { backgroundColor: th.color + "1c", flexDirection: rtl ? "row-reverse" : "row" }]}>
          <Text style={{ fontSize: 10 }}>{th.emoji}</Text>
          <Text style={[s.historyBadgeText, { color: th.color }]}>{th.label}</Text>
        </View>
        <Text style={s.historyMeta} numberOfLines={1}>
          {platformName(item.url, t)} · {item.timestamp}
        </Text>
      </View>
      <View style={[s.historyPctWrap, { borderColor: th.color + "55" }]}>
        <Text style={[s.historyPct, { color: th.color }]}>{Math.round(item.confidence * 100)}%</Text>
      </View>
    </TouchableOpacity>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
function AppInner() {
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [showPremium, setShowPremium] = useState(false);
  const [scansTotal, setScansTotal] = useState(0);
  const [showHow, setShowHow] = useState(false);
  const [urlText, setUrlText] = useState("");
  const [lang, setLangState] = useState<Lang>("he");
  const t = T[lang];
  const rtl = lang === "he";
  const lastChecked = useRef<string>("");

  const { overlayActive, status, startOverlay, stopOverlay } = useOverlay();

  // NOTE: we deliberately do NOT auto-start the overlay on launch. Starting a
  // specialUse foreground service at app startup crashes the process on
  // Android 14+ (ForegroundServiceStartNotAllowed / DidNotStartInTime — thrown
  // by the framework, uncatchable). The overlay starts ONLY from the toggle.

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    SecureStore.setItemAsync(LANG_KEY, l).catch(() => {});
  }, []);

  // ── Persistence: history + language survive restarts ──
  useEffect(() => {
    (async () => {
      try {
        const l = await SecureStore.getItemAsync(LANG_KEY);
        if (l === "he" || l === "en") setLangState(l);
      } catch {}
      try {
        const info = await FileSystem.getInfoAsync(HISTORY_FILE);
        if (info.exists) {
          const raw = await FileSystem.readAsStringAsync(HISTORY_FILE);
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed.items)) setHistory(parsed.items.filter((h: HistoryItem) => !h.loading));
          if (typeof parsed.scans === "number") setScansTotal(parsed.scans);
        }
      } catch {}
      setHistoryLoaded(true);
    })();
  }, []);

  useEffect(() => {
    if (!historyLoaded) return;
    const items = history.filter((h) => !h.loading).slice(0, 50);
    FileSystem.writeAsStringAsync(HISTORY_FILE, JSON.stringify({ items, scans: scansTotal }))
      .catch(() => {});
  }, [history, scansTotal, historyLoaded]);

  // ── Staged loading text ──
  useEffect(() => {
    if (!loading) { setStage(0); return; }
    const id = setInterval(() => setStage((n) => Math.min(n + 1, t.stages.length - 1)), 7000);
    return () => clearInterval(id);
  }, [loading, t.stages.length]);

  // ── Premium nudge: after 3 scans, then every 7 ──
  useEffect(() => {
    if (scansTotal === 3 || (scansTotal > 3 && scansTotal % 7 === 0)) {
      const id = setTimeout(() => setShowPremium(true), 1200);
      return () => clearTimeout(id);
    }
  }, [scansTotal]);

  const detect = useCallback(async (url: string) => {
    setLoading(true);
    setSelected(null);
    Vibration.vibrate(30);
    const loadingItem: HistoryItem = {
      is_ai_generated: false, verdict: "real", confidence: 0,
      ai_tool_detected: null, edit_tool_detected: null, detection_method: "",
      timestamp: new Date().toLocaleTimeString(rtl ? "he-IL" : "en-US", { hour: "2-digit", minute: "2-digit" }),
      url, loading: true,
    };
    setHistory((prev) => [loadingItem, ...prev.filter((h) => !h.loading).slice(0, 49)]);
    try {
      const data = await detectVideoUrl(url);
      const item: HistoryItem = {
        ...data,
        timestamp: new Date().toLocaleTimeString(rtl ? "he-IL" : "en-US", { hour: "2-digit", minute: "2-digit" }),
        url,
      };
      setHistory((prev) => [item, ...prev.filter((h) => !h.loading).slice(0, 49)]);
      setSelected(item);
      setScansTotal((n) => n + 1);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch (e: unknown) {
      setHistory((prev) => prev.filter((h) => !h.loading));
      const emsg = e instanceof Error ? e.message : "";
      const downloadIssue = !emsg || /download|fetch|network|timeout|could not|5\d\d|blocked|failed/i.test(emsg);
      if (downloadIssue) {
        Alert.alert(
          lang === "he" ? "לא הצלחתי לשלוף את הסרטון מהקישור" : "Couldn't fetch the video from the link",
          lang === "he"
            ? "יוטיוב/טיקטוק לפעמים חוסמים שליפה אוטומטית. הדרך הכי בטוחה שתמיד עובדת:\n\nפתח את הסרטון ← שתף (Share) ← VerifAI"
            : "YouTube/TikTok sometimes block automatic fetching. The most reliable way:\n\nOpen the video → Share → VerifAI",
          [{ text: lang === "he" ? "הבנתי" : "Got it" }]
        );
      } else {
        Alert.alert(T[lang].error, emsg || T[lang].connError);
      }
    } finally {
      setLoading(false);
    }
  }, [lang, rtl]);

  const detectVideoFile = useCallback(async (uri: string, mimeType = "video/mp4") => {
    setLoading(true);
    setSelected(null);
    Vibration.vibrate(30);
    const loadingItem: HistoryItem = {
      is_ai_generated: false, verdict: "real", confidence: 0,
      ai_tool_detected: null, edit_tool_detected: null, detection_method: "",
      timestamp: new Date().toLocaleTimeString(rtl ? "he-IL" : "en-US", { hour: "2-digit", minute: "2-digit" }),
      url: uri, loading: true,
    };
    setHistory((prev) => [loadingItem, ...prev.filter((h) => !h.loading).slice(0, 49)]);
    try {
      const { detectVideoFileUpload } = await import("./services/detector");
      const data = await detectVideoFileUpload(uri, mimeType);
      const item: HistoryItem = {
        ...data,
        timestamp: new Date().toLocaleTimeString(rtl ? "he-IL" : "en-US", { hour: "2-digit", minute: "2-digit" }),
        url: uri,
      };
      setHistory((prev) => [item, ...prev.filter((h) => !h.loading).slice(0, 49)]);
      setSelected(item);
      setScansTotal((n) => n + 1);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch {
      setHistory((prev) => prev.filter((h) => !h.loading));
    } finally {
      setLoading(false);
    }
  }, [lang, rtl]);

  // Clipboard auto-detect when app comes foreground
  useEffect(() => {
    const sub = AppState.addEventListener("change", async (state: string) => {
      if (state !== "active") return;
      try {
        const text = await Clipboard.getStringAsync();
        if (text && text !== lastChecked.current && isVideoUrl(text)) {
          lastChecked.current = text;
          detect(text);
        }
      } catch {}
    });
    return () => sub.remove();
  }, [detect]);

  // Video FILES shared from TikTok/Instagram (Share → VerifAI)
  useEffect(() => {
    const { NativeModules } = require("react-native");
    const IntentModule = NativeModules.IntentModule || NativeModules.RNIntentModule;
    if (IntentModule?.getInitialIntent) {
      IntentModule.getInitialIntent().then((intent: { uri?: string; type?: string }) => {
        const mime = intent?.type || "";
        if (intent?.uri && (mime.startsWith("video/") || mime.startsWith("image/"))) {
          detectVideoFile(intent.uri, mime);
        }
      }).catch(() => {});
    }
  }, []);

  // Deep links / shared URLs
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

  const submitUrl = useCallback(() => {
    const u = urlText.trim();
    if (!u.startsWith("http")) {
      Alert.alert(t.error, t.invalidLink);
      return;
    }
    setUrlText("");
    detect(u);
  }, [urlText, detect, t]);

  const pasteFromClipboard = useCallback(async () => {
    try {
      const text = await Clipboard.getStringAsync();
      if (text?.startsWith("http")) {
        setUrlText(text.trim());
      } else {
        Alert.alert(t.copyFirst, t.copyHint, [{ text: t.understood }]);
      }
    } catch {
      Alert.alert(t.error, t.clipboardError);
    }
  }, [t]);

  const counts = useMemo(() => {
    const real = history.filter((h) => !h.loading && verdictOf(h) === "real").length;
    const ai = history.filter((h) => !h.loading && verdictOf(h) === "ai_generated").length;
    const edited = history.filter((h) => !h.loading && verdictOf(h) === "ai_edited").length;
    return { ai, edited, real };
  }, [history]);

  const row = { flexDirection: (rtl ? "row-reverse" : "row") as "row-reverse" | "row" };
  const align = { textAlign: (rtl ? "right" : "left") as "right" | "left" };
  const howSteps = Platform.OS === "android" ? t.howSteps : t.howIos;

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />

      {/* brand glow behind the header — pure depth, non-interactive */}
      <LinearGradient
        colors={["#2a0e63", "#1a0838", "rgba(7,3,22,0)"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.heroGlow}
        pointerEvents="none"
      />

      {selected && !selected.loading && (
        <ResultSheet item={selected} onClose={() => setSelected(null)} onRecheck={detect} lang={lang} />
      )}
      <PremiumModal visible={showPremium} onClose={() => setShowPremium(false)} lang={lang} />
      <WhatsNew />{/* only on the home screen — never over onboarding/crash */}

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        {/* ── Header ── */}
        <View style={[s.headerTop, row]}>
          <View style={[{ alignItems: "center", gap: 10 }, row]}>
            <LinearGradient colors={GRAD} start={GRAD_START} end={GRAD_END} style={s.logoMark}>
              <Text style={s.logoMarkText}>V</Text>
            </LinearGradient>
            <View>
              <Text style={[s.headerTitle, align]}>VerifAI</Text>
              <Text style={[s.headerVersion, align]}>v{APP_VERSION}</Text>
            </View>
          </View>
          <View style={[{ gap: 8, alignItems: "center" }, row]}>
            <TouchableOpacity style={s.langBtn} onPress={() => setLang(lang === "he" ? "en" : "he")}>
              <Text style={s.langBtnText}>{lang === "he" ? "EN" : "עב"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.proBtn} onPress={() => setShowPremium(true)}>
              <Text style={s.proBtnText}>👑 Pro</Text>
            </TouchableOpacity>
          </View>
        </View>
        <Text style={[s.tagline, align]}>{t.tagline}</Text>

        {/* ── Detect card: paste a link → get an answer ── */}
        <View style={s.detectCard}>
          <Text style={[s.detectTitle, align]}>{t.detectTitle}</Text>
          <Text style={[s.detectSub, align]}>{t.detectSub}</Text>
          <View style={[s.inputRow, row]}>
            <TextInput
              style={[s.input, align]}
              value={urlText}
              onChangeText={setUrlText}
              placeholder={t.pastePlaceholder}
              placeholderTextColor={C.faint}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              returnKeyType="go"
              onSubmitEditing={submitUrl}
            />
            {urlText.length === 0 ? (
              <TouchableOpacity style={s.pasteBtn} onPress={pasteFromClipboard} activeOpacity={0.8}>
                <Text style={s.pasteBtnText}>{t.pasteBtn}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity style={s.clearInputBtn} onPress={() => setUrlText("")} activeOpacity={0.8}>
                <Text style={s.clearInputText}>✕</Text>
              </TouchableOpacity>
            )}
          </View>
          <TouchableOpacity
            style={[s.detectBtnWrap, (loading || !urlText.trim()) && s.detectBtnDisabled]}
            onPress={submitUrl}
            disabled={loading || !urlText.trim()}
            activeOpacity={0.85}
          >
           <LinearGradient colors={GRAD} start={GRAD_START} end={GRAD_END} style={s.detectBtn}>
            {loading ? (
              <View style={[{ alignItems: "center", gap: 8 }, row]}>
                <ActivityIndicator size="small" color="#fff" />
                <Text style={s.detectBtnText}>{t.stages[stage]}</Text>
              </View>
            ) : (
              <Text style={s.detectBtnText}>🛡️  {t.detectNow}</Text>
            )}
           </LinearGradient>
          </TouchableOpacity>
          <Text style={s.detectHint}>{t.detectTip}</Text>
        </View>

        {/* ── Stats ── */}
        {history.length > 0 && (
          <View style={[s.statsRow, row]}>
            <View style={[s.statBox, { borderColor: C.ai + "33" }]}>
              <Text style={[s.statNum, { color: C.ai }]}>{counts.ai}</Text>
              <Text style={s.statLabel}>🤖 {t.statAI}</Text>
            </View>
            <View style={[s.statBox, { borderColor: C.edited + "33" }]}>
              <Text style={[s.statNum, { color: C.edited }]}>{counts.edited}</Text>
              <Text style={s.statLabel}>🎭 {t.statEdited}</Text>
            </View>
            <View style={[s.statBox, { borderColor: C.real + "33" }]}>
              <Text style={[s.statNum, { color: C.real }]}>{counts.real}</Text>
              <Text style={s.statLabel}>✅ {t.statReal}</Text>
            </View>
          </View>
        )}

        {/* ── Control center (Android) ── */}
        {Platform.OS === "android" && (
          <StatusCard
            status={status}
            overlayActive={overlayActive}
            onToggle={(v) => (v ? startOverlay() : stopOverlay())}
            lang={lang}
          />
        )}

        {/* ── How it works (collapsible) ── */}
        <TouchableOpacity style={s.card} onPress={() => setShowHow(!showHow)} activeOpacity={0.8}>
          <View style={[{ justifyContent: "space-between", alignItems: "center" }, row]}>
            <Text style={[s.cardTitle, align]}>💡 {t.howTitle}</Text>
            <Text style={s.chevron}>{showHow ? "▴" : "▾"}</Text>
          </View>
          {showHow && (
            <View style={{ gap: 10, marginTop: 12 }}>
              {howSteps.map((step, i) => (
                <View key={i} style={[{ alignItems: "center", gap: 10 }, row]}>
                  <View style={s.stepNum}><Text style={s.stepNumText}>{i + 1}</Text></View>
                  <Text style={[s.stepText, align, { flex: 1 }]}>{step}</Text>
                </View>
              ))}
              <Text style={[s.cardTitle, align, { marginTop: 10, fontSize: 13, color: "#c9c3ff" }]}>
                {t.howKnowTitle}
              </Text>
              {t.howKnowRows.map(([icon, text], i) => (
                <View key={`k${i}`} style={[{ alignItems: "flex-start", gap: 10 }, row]}>
                  <Text style={s.howIcon}>{icon}</Text>
                  <Text style={[s.stepText, align, { flex: 1 }]}>{text}</Text>
                </View>
              ))}
            </View>
          )}
        </TouchableOpacity>

        {/* ── Premium banner ── */}
        <TouchableOpacity style={[s.premiumBanner, row]} onPress={() => setShowPremium(true)} activeOpacity={0.85}>
          <View>
            <Text style={[s.premiumBannerTitle, align]}>👑 {t.premiumBannerTitle}</Text>
            <Text style={[s.premiumBannerSub, align]}>{t.premiumBannerSub}</Text>
          </View>
          <View style={s.premiumArrow}>
            <Text style={{ color: "#fff", fontSize: 13 }}>{rtl ? "←" : "→"}</Text>
          </View>
        </TouchableOpacity>

        {/* ── History ── */}
        {history.length > 0 ? (
          <View style={{ gap: 10 }}>
            <View style={[{ justifyContent: "space-between", alignItems: "center" }, row]}>
              <Text style={[s.sectionTitle, align]}>{t.history}</Text>
              <TouchableOpacity onPress={() => setHistory([])}>
                <Text style={s.clearBtn}>{t.clearAll}</Text>
              </TouchableOpacity>
            </View>
            {history.map((item, i) =>
              item.loading ? (
                <View key="loading" style={[s.historyRow, row, { padding: 14, gap: 10, alignItems: "center" }]}>
                  <ActivityIndicator size="small" color={C.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={[{ color: C.primary, fontWeight: "700", fontSize: 13 }, align]}>{t.scanning}</Text>
                    <Text style={[s.historyMeta, align]} numberOfLines={1}>{platformName(item.url, t)}</Text>
                  </View>
                </View>
              ) : (
                <HistoryRow key={`${item.url}-${i}`} item={item} onPress={() => setSelected(item)} lang={lang} />
              )
            )}
          </View>
        ) : (
          <View style={s.empty}>
            <Text style={s.emptyIcon}>🎬</Text>
            <Text style={s.emptyTitle}>{t.empty}</Text>
            <Text style={s.emptyHint}>
              {Platform.OS === "android" ? t.emptyHint.android : t.emptyHint.ios}
            </Text>
          </View>
        )}

        {/* Self-check: which Expo project/channel/update this install really runs */}
        <SelfCheck version={APP_VERSION} />

        <TouchableOpacity onPress={() => Linking.openURL(DOWNLOAD_URL)} style={s.downloadLink}>
          <Text style={s.downloadText}>📲 {t.downloadText}</Text>
        </TouchableOpacity>

      </ScrollView>
    </SafeAreaView>
  );
}

// ─── "What's New" — shown once when the app picked up a newer changelog entry
// (delivered live via OTA). Fresh installs record the current version silently
// so only a genuine future update pops it. ─────────────────────────────────────
const WHATS_NEW_KEY = "verifai_whatsnew_seen";

function WhatsNew() {
  const [visible, setVisible] = useState(false);
  const entry = CHANGELOG[0];

  useEffect(() => {
    let alive = true;
    SecureStore.getItemAsync(WHATS_NEW_KEY)
      .then((seen) => {
        if (!alive || !entry) return;
        if (seen === null || seen === undefined) {
          SecureStore.setItemAsync(WHATS_NEW_KEY, CHANGELOG_VERSION).catch(() => {});
          return;
        }
        if (seen !== CHANGELOG_VERSION) setVisible(true);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const dismiss = useCallback(() => {
    setVisible(false);
    SecureStore.setItemAsync(WHATS_NEW_KEY, CHANGELOG_VERSION).catch(() => {});
  }, []);

  if (!visible || !entry) return null;
  return (
    <Modal visible transparent animationType="fade" onRequestClose={dismiss}>
      <View style={wn.backdrop}>
        <View style={wn.card}>
          <Text style={wn.badge}>✨ עודכן · What&apos;s New</Text>
          <Text style={wn.title}>{entry.title}</Text>
          <Text style={wn.date}>{entry.date}</Text>
          <ScrollView style={{ maxHeight: 320 }} showsVerticalScrollIndicator={false}>
            {entry.items.map((it, i) => (
              <View key={i} style={wn.row}>
                <Text style={wn.dot}>›</Text>
                <Text style={wn.item}>{it}</Text>
              </View>
            ))}
          </ScrollView>
          <TouchableOpacity style={wn.btn} onPress={dismiss} activeOpacity={0.85}>
            <Text style={wn.btnText}>מעולה · Got it</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const wn = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "#03030ad1", justifyContent: "center", alignItems: "center", padding: 22 },
  card: { width: "100%", maxWidth: 440, backgroundColor: C.card, borderRadius: 24, borderWidth: 1, borderColor: C.primary + "59", padding: 22 },
  badge: { color: "#a99bff", fontSize: 12, fontWeight: "700", letterSpacing: 1, marginBottom: 10 },
  title: { color: C.text, fontSize: 21, fontWeight: "800" },
  date: { color: C.faint, fontSize: 12, marginTop: 2, marginBottom: 14 },
  row: { flexDirection: "row", gap: 8, marginBottom: 10, alignItems: "flex-start" },
  dot: { color: C.primary, fontSize: 15, fontWeight: "800", lineHeight: 21 },
  item: { color: "#c9cae0", fontSize: 14, lineHeight: 21, flex: 1 },
  btn: { marginTop: 16, backgroundColor: C.primaryDeep, borderRadius: 16, paddingVertical: 13, alignItems: "center" },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});

// ─── Crash visibility ─────────────────────────────────────────────────────────
// Any fatal JS error is persisted so the next launch SHOWS it instead of a
// blank screen. Native services write to verifai_crash.txt (see CrashLog.java).

const g: any = global as any;
if (g.ErrorUtils && !g.__verifaiErrHandler) {
  g.__verifaiErrHandler = true;
  const prev = g.ErrorUtils.getGlobalHandler?.();
  g.ErrorUtils.setGlobalHandler?.((e: any, isFatal?: boolean) => {
    try { SecureStore.setItemAsync(JS_ERROR_KEY, String(e?.stack || e).slice(0, 4000)).catch(() => {}); } catch {}
    prev?.(e, isFatal);
  });
}

function ErrorScreen({ title, text, onDismiss }: { title: string; text: string; onDismiss: () => void }) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg, padding: 20 }}>
      <Text style={{ color: C.ai, fontSize: 18, fontWeight: "800", marginTop: 30, textAlign: "right" }}>{title}</Text>
      <Text style={{ color: C.sub, fontSize: 12, marginTop: 6, textAlign: "right" }}>
        צלם מסך של העמוד הזה ושלח — זה בדיוק מה שצריך כדי לתקן. v{APP_VERSION}
      </Text>
      <ScrollView style={{ marginTop: 14, flex: 1 }}>
        <Text selectable style={{ color: "#e5e7eb", fontSize: 11, fontFamily: Platform.OS === "android" ? "monospace" : "Menlo" }}>
          {text}
        </Text>
      </ScrollView>
      <TouchableOpacity
        onPress={onDismiss}
        style={{ backgroundColor: C.primaryDeep, borderRadius: 14, padding: 16, alignItems: "center", marginTop: 12 }}
      >
        <Text style={{ color: "#fff", fontWeight: "700" }}>המשך לאפליקציה</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: any) {
    try { SecureStore.setItemAsync(JS_ERROR_KEY, (String(error?.stack || error) + "\n" + String(info?.componentStack || "")).slice(0, 4000)).catch(() => {}); } catch {}
  }
  render() {
    if (this.state.error) {
      return (
        <ErrorScreen
          title="😵 האפליקציה נתקלה בשגיאה"
          text={String(this.state.error?.stack || this.state.error)}
          onDismiss={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}

function useStoredCrashLogs(): [string | null, () => void] {
  const [log, setLog] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      let combined = "";
      try {
        const js = await SecureStore.getItemAsync(JS_ERROR_KEY);
        if (js) {
          combined += "── שגיאת JS מהריצה הקודמת ──\n" + js + "\n\n";
          SecureStore.deleteItemAsync(JS_ERROR_KEY).catch(() => {});
        }
      } catch {}
      try {
        const path = FileSystem.documentDirectory + "verifai_crash.txt";
        const info = await FileSystem.getInfoAsync(path);
        if (info.exists) {
          const native = await FileSystem.readAsStringAsync(path);
          if (native?.trim()) combined += "── שגיאה נייטיבית ──\n" + native.slice(-3000);
          FileSystem.deleteAsync(path, { idempotent: true }).catch(() => {});
        }
      } catch {}
      if (combined) setLog(combined);
    })();
  }, []);
  return [log, () => setLog(null)];
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppRouter />
    </ErrorBoundary>
  );
}

function AppRouter() {
  // Crash from a previous run? Show it before anything else.
  const [crashLog, dismissCrashLog] = useStoredCrashLogs();
  if (crashLog) {
    return <ErrorScreen title="🛠️ נתפסה שגיאה מהריצה הקודמת" text={crashLog} onDismiss={dismissCrashLog} />;
  }

  // Onboarding is no longer a hard gate: the overlay/accessibility permissions
  // are optional (offered inside the app via the control-center card), so the
  // permission flow can never block or loop the user out of the app.
  return <AppInner />;
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  heroGlow: { position: "absolute", top: 0, left: 0, right: 0, height: 300 },
  scroll: { padding: 18, paddingBottom: 60, gap: 16 },

  // Header
  headerTop: { justifyContent: "space-between", alignItems: "center" },
  logoMark: {
    width: 48, height: 48, borderRadius: 15, alignItems: "center", justifyContent: "center",
    backgroundColor: C.primary, borderWidth: 1.5, borderColor: "#ffffff33",
    shadowColor: C.magenta, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.85, shadowRadius: 18, elevation: 12,
  },
  logoMarkText: { color: "#fff", fontSize: 26, fontWeight: "900", letterSpacing: -1 },
  headerTitle: { color: C.text, fontSize: 30, fontWeight: "900", letterSpacing: -1 },
  headerVersion: { color: C.faint, fontSize: 10, fontWeight: "600", letterSpacing: 1 },
  tagline: { color: C.sub, fontSize: 14, marginTop: -6 },
  langBtn: { backgroundColor: C.card, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.border },
  langBtnText: { color: C.sub, fontSize: 11, fontWeight: "700" },
  proBtn: { backgroundColor: "#171130", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: C.violet + "55" },
  proBtnText: { color: "#c4b5fd", fontSize: 12, fontWeight: "700" },

  // Detect card (paste a link → answer)
  detectCard: {
    backgroundColor: C.card, borderRadius: 24, padding: 18, gap: 10,
    borderWidth: 1.5, borderColor: C.primary + "66",
    shadowColor: C.primary, shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.4, shadowRadius: 28, elevation: 10,
  },
  detectTitle: { color: C.text, fontSize: 19, fontWeight: "800" },
  detectSub: { color: C.sub, fontSize: 12.5, marginTop: -4 },
  inputRow: { gap: 8, alignItems: "center", marginTop: 4 },
  input: {
    flex: 1, backgroundColor: "#ffffff0d", borderRadius: 14,
    borderWidth: 1, borderColor: "#ffffff1f",
    paddingHorizontal: 14, paddingVertical: 12, color: C.text, fontSize: 14,
  },
  pasteBtn: {
    backgroundColor: C.primary + "26", borderRadius: 12,
    paddingHorizontal: 16, paddingVertical: 12,
    borderWidth: 1, borderColor: C.primary + "66",
  },
  pasteBtnText: { color: "#c9c3ff", fontWeight: "700", fontSize: 13 },
  clearInputBtn: {
    width: 40, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center",
    backgroundColor: "#ffffff0f", borderWidth: 1, borderColor: "#ffffff1f",
  },
  clearInputText: { color: C.sub, fontSize: 15, fontWeight: "700" },
  detectBtnWrap: {
    marginTop: 4, borderRadius: 16,
    shadowColor: C.magenta, shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.7, shadowRadius: 22, elevation: 12,
  },
  detectBtn: {
    borderRadius: 16, paddingVertical: 16, alignItems: "center",
    borderWidth: 1, borderColor: "#ffffff2e",
  },
  detectBtnDisabled: { opacity: 0.4 },
  detectBtnText: { color: "#fff", fontWeight: "900", fontSize: 17, letterSpacing: 0.2 },
  detectHint: { color: C.faint, fontSize: 11, textAlign: "center", marginTop: 2 },

  // How-it-works explainer
  howIcon: { fontSize: 17, width: 26, textAlign: "center" },

  // Stats
  statsRow: { gap: 10 },
  statBox: { flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 12, alignItems: "center", borderWidth: 1 },
  statNum: { fontSize: 22, fontWeight: "800" },
  statLabel: { color: C.faint, fontSize: 10, fontWeight: "600", marginTop: 2 },

  // Card
  card: { backgroundColor: C.card, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: C.border },
  cardTitle: { color: C.text, fontWeight: "800", fontSize: 15 },
  chevron: { color: C.faint, fontSize: 14 },

  stepNum: { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center", backgroundColor: C.primaryDeep },
  stepNumText: { color: "#fff", fontSize: 11, fontWeight: "800" },
  stepText: { color: C.sub, fontSize: 13, lineHeight: 19 },

  // Premium banner
  premiumBanner: {
    justifyContent: "space-between", alignItems: "center",
    borderRadius: 18, padding: 16,
    backgroundColor: "#140d2c",
    borderWidth: 1, borderColor: C.violet + "50",
  },
  premiumBannerTitle: { color: "#d6c9ff", fontSize: 15, fontWeight: "800" },
  premiumBannerSub: { color: "#7f6bd6", fontSize: 12, marginTop: 3 },
  premiumArrow: { backgroundColor: C.violet, borderRadius: 12, width: 30, height: 30, alignItems: "center", justifyContent: "center" },

  // Section
  sectionTitle: { color: C.sub, fontSize: 12, fontWeight: "800", letterSpacing: 1 },
  clearBtn: { color: C.faint, fontSize: 12 },

  // History
  historyRow: { alignItems: "center", backgroundColor: C.card, borderRadius: 16, overflow: "hidden", borderWidth: 1, borderColor: C.border },
  historyBar: { width: 4, alignSelf: "stretch" },
  historyInfo: { flex: 1, gap: 5, padding: 13 },
  historyBadge: { alignItems: "center", gap: 5, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  historyBadgeText: { fontSize: 11, fontWeight: "800" },
  historyMeta: { color: C.faint, fontSize: 11 },
  historyPctWrap: { marginHorizontal: 13, width: 48, height: 48, borderRadius: 24, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  historyPct: { fontSize: 13, fontWeight: "900" },

  // Empty
  empty: { alignItems: "center", paddingVertical: 40, gap: 12 },
  emptyIcon: { fontSize: 56, opacity: 0.7 },
  emptyTitle: { color: C.sub, fontSize: 16, fontWeight: "700" },
  emptyHint: { color: C.faint, fontSize: 13, textAlign: "center", lineHeight: 20, paddingHorizontal: 32 },

  downloadLink: { alignItems: "center", paddingVertical: 12 },
  downloadText: { color: C.faint, fontSize: 12 },
});

// Status card styles
const st = StyleSheet.create({
  header: { justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  row: { alignItems: "center", gap: 10, paddingVertical: 7 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowLabel: { color: C.sub, fontSize: 13 },
  okText: { color: C.real, fontSize: 12, fontWeight: "700" },
  offText: { color: C.faint, fontSize: 12 },
  fixBtn: { backgroundColor: C.primaryDeep, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 6 },
  fixText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  allGood: { color: C.real, fontSize: 12, marginTop: 8, lineHeight: 18 },
});

// Result sheet styles
const rs = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "#000000b8", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: "#0b0d1c", borderTopLeftRadius: 28, borderTopRightRadius: 28,
    padding: 20, paddingBottom: 36, gap: 14,
    borderWidth: 1, borderColor: C.border,
  },
  grabber: { width: 40, height: 4, borderRadius: 2, backgroundColor: "#ffffff22", alignSelf: "center", marginBottom: 2 },
  header: { alignItems: "center", borderRadius: 20, borderWidth: 1, padding: 18, gap: 4 },
  headerEmoji: { fontSize: 40 },
  headerLabel: { fontSize: 22, fontWeight: "900", letterSpacing: -0.3 },
  headerTool: { color: C.sub, fontSize: 13, fontWeight: "600" },
  fastBadge: { color: "#6ee7b7", fontSize: 11, fontWeight: "700", marginTop: 2 },
  timeline: { flexDirection: "row", alignItems: "flex-end", gap: 1.5, height: 20, marginTop: 6 },
  caveat: { color: "#b58a4a", fontSize: 11, lineHeight: 16, marginTop: 4 },

  confWrap: { gap: 8 },
  confRow: { justifyContent: "space-between", alignItems: "center" },
  confLabel: { color: C.sub, fontSize: 13, fontWeight: "600" },
  confPct: { fontSize: 20, fontWeight: "900" },
  confTrack: { height: 8, borderRadius: 4, backgroundColor: "#ffffff10", overflow: "hidden" },
  confFill: { height: 8, borderRadius: 4 },

  meaning: { color: C.sub, fontSize: 13, lineHeight: 20 },

  details: { backgroundColor: "#ffffff06", borderRadius: 16, padding: 14, gap: 8 },
  detailRow: { gap: 10, alignItems: "flex-start" },
  detailKey: { color: C.faint, fontSize: 11, fontWeight: "700", minWidth: 60 },
  detailVal: { color: C.sub, fontSize: 12, flex: 1, lineHeight: 17 },
  layerRow: { alignItems: "center", gap: 8 },
  layerName: { color: C.faint, fontSize: 10, width: 84 },
  layerTrack: { flex: 1, height: 5, borderRadius: 3, backgroundColor: "#ffffff10", overflow: "hidden" },
  layerFill: { height: 5, borderRadius: 3 },
  layerPct: { color: C.sub, fontSize: 10, width: 32, textAlign: "center" },
  urlLine: { color: C.faint, fontSize: 10, marginTop: 4 },

  actions: { gap: 10 },
  actionBtn: {
    flex: 1, borderRadius: 15, paddingVertical: 14, alignItems: "center",
    backgroundColor: "#ffffff0c", borderWidth: 1, borderColor: C.border,
  },
  actionPrimary: { backgroundColor: C.primaryDeep, borderColor: "transparent" },
  actionText: { color: C.sub, fontSize: 14, fontWeight: "700" },
  actionPrimaryText: { color: "#fff", fontSize: 14, fontWeight: "800" },
});

// Premium modal styles
const pm = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "#000000cc", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: "#0d0d1e", borderTopLeftRadius: 30, borderTopRightRadius: 30,
    paddingBottom: 36, overflow: "hidden",
    borderWidth: 1, borderColor: C.border,
  },
  header: { backgroundColor: "#130b2e", padding: 26, alignItems: "center", gap: 6 },
  crownWrap: { width: 60, height: 60, borderRadius: 30, backgroundColor: C.violet + "30", alignItems: "center", justifyContent: "center", marginBottom: 4 },
  headerTitle: { color: "#fff", fontSize: 24, fontWeight: "900", letterSpacing: -0.5 },
  headerSub: { color: "#8b74e8", fontSize: 13, textAlign: "center", lineHeight: 18 },

  features: { padding: 20, gap: 14 },
  featureRow: { alignItems: "center", gap: 13 },
  featureIcon: { width: 40, height: 40, borderRadius: 12, backgroundColor: "#1b1040", alignItems: "center", justifyContent: "center" },
  featureTitle: { color: C.text, fontSize: 14, fontWeight: "700" },
  featureDesc: { color: C.faint, fontSize: 12, marginTop: 1 },
  checkmark: { color: C.violet, fontSize: 17, fontWeight: "800" },

  priceRow: { justifyContent: "space-between", alignItems: "center", paddingHorizontal: 20, marginBottom: 16 },
  price: { color: "#fff", fontSize: 34, fontWeight: "900" },
  pricePer: { color: C.faint, fontSize: 14, marginBottom: 7 },
  badge: { backgroundColor: C.violet + "22", borderRadius: 12, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderColor: C.violet + "55" },
  badgeText: { color: "#c4b5fd", fontSize: 13, fontWeight: "700" },

  cta: {
    marginHorizontal: 18, borderRadius: 16, padding: 17, alignItems: "center",
    backgroundColor: C.violet,
    shadowColor: C.violet, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.5, shadowRadius: 16, elevation: 10,
  },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  skip: { alignItems: "center", paddingVertical: 14 },
  skipText: { color: C.faint, fontSize: 14 },
});
