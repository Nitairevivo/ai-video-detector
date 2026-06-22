import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  View, Text, StyleSheet, Animated, TouchableOpacity,
  Platform, SafeAreaView, StatusBar, ScrollView,
  Alert, AppState, Vibration, TextInput, KeyboardAvoidingView,
} from "react-native";
import * as Clipboard from "expo-clipboard";

const API = "https://ai-video-detector-production-a305.up.railway.app";

// Platforms with known video URL patterns — auto-detected from clipboard
const VIDEO_URL_PATTERNS: { pattern: RegExp; name: string }[] = [
  { pattern: /tiktok\.com/, name: "TikTok" },
  { pattern: /instagram\.com\/(reel|p|tv)\//, name: "Instagram" },
  { pattern: /youtube\.com\/(shorts|watch|live)/, name: "YouTube" },
  { pattern: /youtu\.be\//, name: "YouTube" },
  { pattern: /twitter\.com\/.*\/status/, name: "Twitter/X" },
  { pattern: /x\.com\/.*\/status/, name: "Twitter/X" },
  { pattern: /reddit\.com\/r\/.*\/comments/, name: "Reddit" },
  { pattern: /v\.redd\.it\//, name: "Reddit" },
  { pattern: /facebook\.com\/(watch|reel|videos)/, name: "Facebook" },
  { pattern: /fb\.watch\//, name: "Facebook" },
  { pattern: /t\.me\//, name: "Telegram" },
  { pattern: /snapchat\.com\//, name: "Snapchat" },
  { pattern: /pin\.it\//, name: "Pinterest" },
  { pattern: /pinterest\.com\/pin\//, name: "Pinterest" },
  { pattern: /twitch\.tv\//, name: "Twitch" },
  { pattern: /clips\.twitch\.tv\//, name: "Twitch" },
  { pattern: /vimeo\.com\//, name: "Vimeo" },
  { pattern: /dailymotion\.com\/video/, name: "Dailymotion" },
  { pattern: /triller\.co\//, name: "Triller" },
  { pattern: /likee\.video\//, name: "Likee" },
  { pattern: /kwai\.com\//, name: "Kwai" },
  { pattern: /zynn\.com\//, name: "Zynn" },
  { pattern: /rumble\.com\//, name: "Rumble" },
  { pattern: /odysee\.com\//, name: "Odysee" },
  { pattern: /bitchute\.com\/video\//, name: "BitChute" },
  { pattern: /streamable\.com\//, name: "Streamable" },
  { pattern: /imgur\.com\//, name: "Imgur" },
  { pattern: /gfycat\.com\//, name: "Gfycat" },
  { pattern: /medal\.tv\//, name: "Medal" },
  { pattern: /discord\.com\/channels/, name: "Discord" },
  { pattern: /\.mp4(\?|$)/, name: "Direct MP4" },
  { pattern: /\.webm(\?|$)/, name: "Direct WebM" },
  { pattern: /\.mov(\?|$)/, name: "Direct MOV" },
];

function detectPlatform(url: string): string | null {
  for (const { pattern, name } of VIDEO_URL_PATTERNS) {
    if (pattern.test(url)) return name;
  }
  return null;
}

function isVideoUrl(url: string) {
  return detectPlatform(url) !== null;
}

type Result = {
  is_ai_generated: boolean;
  confidence: number;
  ai_tool_detected: string | null;
  detection_method: string;
};

type HistoryItem = Result & { timestamp: string; url: string; platform: string };

// ─── Result Banner ────────────────────────────────────────────────────────────

function ResultBanner({ result, onDismiss }: { result: Result; onDismiss: () => void }) {
  const slideY = useRef(new Animated.Value(-140)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideY, { toValue: 0, useNativeDriver: true, tension: 70, friction: 10 }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
    const t = setTimeout(onDismiss, 8000);
    return () => clearTimeout(t);
  }, []);

  const isAI = result.is_ai_generated;
  const pct = Math.round(result.confidence * 100);
  const color = isAI ? "#ef4444" : "#22c55e";
  const bg = isAI ? "#1a0505ee" : "#051a05ee";

  return (
    <Animated.View style={[styles.banner, { backgroundColor: bg, borderColor: color + "66", transform: [{ translateY: slideY }], opacity }]}>
      <View style={[styles.bannerBar, { backgroundColor: color }]} />
      <View style={styles.bannerBody}>
        <View style={styles.bannerLeft}>
          <View style={[styles.bannerBadge, { backgroundColor: color + "22" }]}>
            <View style={[styles.bannerDot, { backgroundColor: color }]} />
            <Text style={[styles.bannerBadgeText, { color }]}>
              {isAI ? "AI GENERATED" : "AUTHENTIC"}
            </Text>
          </View>
          <Text style={styles.bannerTitle}>
            {isAI ? (result.ai_tool_detected ? `Made with ${result.ai_tool_detected}` : "AI-Generated Video") : "Real Footage"}
          </Text>
          <Text style={styles.bannerMethod} numberOfLines={1}>{result.detection_method}</Text>
        </View>
        <View style={[styles.bannerCircle, { borderColor: color }]}>
          <Text style={[styles.bannerPct, { color }]}>{pct}%</Text>
          <Text style={styles.bannerConf}>confidence</Text>
        </View>
      </View>
      <TouchableOpacity style={styles.bannerClose} onPress={onDismiss}>
        <Text style={styles.bannerCloseText}>✕</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

// ─── Platform chip ────────────────────────────────────────────────────────────

const PLATFORM_ICONS: Record<string, string> = {
  "TikTok": "🎵", "Instagram": "📸", "YouTube": "▶️", "Twitter/X": "🐦",
  "Reddit": "🤖", "Facebook": "👤", "Telegram": "✈️", "Snapchat": "👻",
  "Pinterest": "📌", "Twitch": "🟣", "Vimeo": "🎬", "Dailymotion": "📺",
  "Rumble": "🔴", "Discord": "💬", "Triller": "🎤", "Direct MP4": "🎥",
  "Direct WebM": "🎥", "Direct MOV": "🎥",
};

function PlatformChip({ name }: { name: string }) {
  const icon = PLATFORM_ICONS[name] ?? "🌐";
  return (
    <View style={styles.chip}>
      <Text style={styles.chipIcon}>{icon}</Text>
      <Text style={styles.chipText}>{name}</Text>
    </View>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [manualUrl, setManualUrl] = useState("");
  const [tab, setTab] = useState<"scan" | "history">("scan");
  const lastChecked = useRef("");

  // Android: auto-detect when returning to app with a video URL in clipboard
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const sub = AppState.addEventListener("change", async (state) => {
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
  }, []);

  const detect = useCallback(async (url: string) => {
    setLoading(true);
    setResult(null);
    Vibration.vibrate(30);
    const platform = detectPlatform(url) ?? "Other";
    try {
      const res = await fetch(`${API}/detect-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data: Result = await res.json();
      setResult(data);
      setHistory(prev => [{ ...data, timestamp: new Date().toLocaleTimeString(), url, platform }, ...prev.slice(0, 49)]);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch (e: unknown) {
      Alert.alert("Detection Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const checkClipboard = useCallback(async () => {
    try {
      const text = (await Clipboard.getStringAsync()).trim();
      if (!text?.startsWith("http")) {
        Alert.alert(
          "No URL in clipboard",
          "Copy a video link from any app, then tap Scan.",
          [{ text: "OK" }]
        );
        return;
      }
      if (!isVideoUrl(text)) {
        Alert.alert(
          "Analyze this URL?",
          text.slice(0, 120) + (text.length > 120 ? "..." : ""),
          [
            { text: "Cancel", style: "cancel" },
            { text: "Analyze anyway", onPress: () => detect(text) },
          ]
        );
        return;
      }
      detect(text);
    } catch {
      Alert.alert("Error", "Could not read clipboard");
    }
  }, [detect]);

  const submitManual = useCallback(() => {
    const url = manualUrl.trim();
    if (!url.startsWith("http")) {
      Alert.alert("Invalid URL", "Enter a full URL starting with https://");
      return;
    }
    setManualUrl("");
    detect(url);
  }, [manualUrl, detect]);

  const allPlatforms = Object.keys(PLATFORM_ICONS).filter(k => !k.startsWith("Direct"));

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor="#07070f" />

      {result && <ResultBanner result={result} onDismiss={() => setResult(null)} />}

      {/* Tab bar */}
      <View style={styles.tabBar}>
        <TouchableOpacity style={[styles.tabBtn, tab === "scan" && styles.tabBtnActive]} onPress={() => setTab("scan")}>
          <Text style={[styles.tabText, tab === "scan" && styles.tabTextActive]}>Scan</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.tabBtn, tab === "history" && styles.tabBtnActive]} onPress={() => setTab("history")}>
          <Text style={[styles.tabText, tab === "history" && styles.tabTextActive]}>
            History {history.length > 0 ? `(${history.length})` : ""}
          </Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

          {tab === "scan" && (
            <>
              {/* Header */}
              <View style={styles.header}>
                <View style={styles.headerBadge}>
                  <View style={styles.headerDot} />
                  <Text style={styles.headerBadgeText}>LIVE · Model AUC 99.8%</Text>
                </View>
                <Text style={styles.title}>AI Video{"\n"}Detector</Text>
                <Text style={styles.subtitle}>
                  Reads binary signatures inside the file — works on any platform.
                </Text>
              </View>

              {/* Scan from clipboard */}
              <TouchableOpacity
                style={[styles.scanBtn, loading && styles.scanBtnLoading]}
                onPress={checkClipboard}
                activeOpacity={0.85}
                disabled={loading}
              >
                <Text style={styles.scanIcon}>{loading ? "⏳" : "📋"}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.scanText}>{loading ? "Analyzing..." : "Scan from Clipboard"}</Text>
                  <Text style={styles.scanSub}>
                    {loading ? "Reading binary file signatures..." : "Copy a link from any app, then tap here"}
                  </Text>
                </View>
              </TouchableOpacity>

              {/* Manual URL input */}
              <View style={styles.manualCard}>
                <Text style={styles.manualLabel}>Or paste a URL manually</Text>
                <View style={styles.manualRow}>
                  <TextInput
                    style={styles.manualInput}
                    placeholder="https://..."
                    placeholderTextColor="#333"
                    value={manualUrl}
                    onChangeText={setManualUrl}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                    returnKeyType="go"
                    onSubmitEditing={submitManual}
                  />
                  <TouchableOpacity
                    style={[styles.manualBtn, (!manualUrl || loading) && styles.manualBtnDisabled]}
                    onPress={submitManual}
                    disabled={!manualUrl || loading}
                  >
                    <Text style={styles.manualBtnText}>Go</Text>
                  </TouchableOpacity>
                </View>
              </View>

              {/* Supported platforms */}
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Works on 30+ platforms</Text>
                <View style={styles.chipGrid}>
                  {allPlatforms.map(name => (
                    <PlatformChip key={name} name={name} />
                  ))}
                  <View style={styles.chip}>
                    <Text style={styles.chipIcon}>🌐</Text>
                    <Text style={styles.chipText}>Any video URL</Text>
                  </View>
                </View>
              </View>

              {/* How it works */}
              <View style={styles.card}>
                <Text style={styles.cardTitle}>How to use</Text>
                <View style={styles.stepRow}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>1</Text></View>
                  <Text style={styles.stepText}>Open any app (TikTok, YouTube, Telegram, Instagram...)</Text>
                </View>
                <View style={styles.stepRow}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>2</Text></View>
                  <Text style={styles.stepText}>Tap Share → Copy Link on any video</Text>
                </View>
                <View style={styles.stepRow}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>3</Text></View>
                  <Text style={styles.stepText}>Come back here, tap "Scan from Clipboard"</Text>
                </View>
                <View style={styles.stepRow}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>4</Text></View>
                  <Text style={styles.stepText}>Result in 2-4 seconds with confidence %</Text>
                </View>
              </View>
            </>
          )}

          {tab === "history" && (
            <>
              {history.length === 0 ? (
                <View style={styles.empty}>
                  <Text style={styles.emptyIcon}>🎬</Text>
                  <Text style={styles.emptyText}>No scans yet</Text>
                  <Text style={styles.emptySub}>Go to Scan tab to analyze a video</Text>
                </View>
              ) : (
                <>
                  <Text style={styles.sectionTitle}>RECENT SCANS ({history.length})</Text>
                  {history.map((item, i) => {
                    const isAI = item.is_ai_generated;
                    const color = isAI ? "#f97316" : "#22c55e";
                    const pct = Math.round(item.confidence * 100);
                    const icon = PLATFORM_ICONS[item.platform] ?? "🌐";
                    return (
                      <TouchableOpacity key={i} style={styles.historyRow} onPress={() => { setResult(item); setTab("scan"); }}>
                        <View style={[styles.historyDot, { backgroundColor: color }]} />
                        <View style={styles.historyInfo}>
                          <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                            <Text style={{ fontSize: 13 }}>{icon}</Text>
                            <Text style={styles.historyTitle}>
                              {isAI ? (item.ai_tool_detected ? `AI · ${item.ai_tool_detected}` : "AI Generated") : "Authentic"}
                            </Text>
                          </View>
                          <Text style={styles.historyUrl} numberOfLines={1}>{item.url.replace(/https?:\/\/(www\.)?/, "")}</Text>
                          <Text style={styles.historyPlatform}>{item.platform}</Text>
                        </View>
                        <View style={styles.historyRight}>
                          <Text style={[styles.historyPct, { color }]}>{pct}%</Text>
                          <Text style={styles.historyTime}>{item.timestamp}</Text>
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </>
              )}
            </>
          )}

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#07070f" },
  scroll: { padding: 20, paddingBottom: 50, gap: 16 },

  tabBar: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "rgba(255,255,255,0.07)" },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: "center" },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: "#6366f1" },
  tabText: { color: "#444", fontSize: 14, fontWeight: "600" },
  tabTextActive: { color: "#fff" },

  banner: {
    position: "absolute", top: 0, left: 12, right: 12, zIndex: 999,
    borderRadius: 16, borderWidth: 1, overflow: "hidden",
    shadowColor: "#000", shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5, shadowRadius: 20, elevation: 20,
  },
  bannerBar: { height: 3 },
  bannerBody: { flexDirection: "row", alignItems: "center", padding: 14, gap: 12 },
  bannerLeft: { flex: 1, gap: 4 },
  bannerBadge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  bannerDot: { width: 5, height: 5, borderRadius: 3 },
  bannerBadgeText: { fontSize: 9, fontWeight: "800", letterSpacing: 1 },
  bannerTitle: { color: "#fff", fontSize: 15, fontWeight: "700" },
  bannerMethod: { color: "#666", fontSize: 11 },
  bannerCircle: { width: 60, height: 60, borderRadius: 30, borderWidth: 2.5, alignItems: "center", justifyContent: "center" },
  bannerPct: { fontSize: 18, fontWeight: "800" },
  bannerConf: { color: "#555", fontSize: 8 },
  bannerClose: { position: "absolute", top: 10, right: 10, padding: 4 },
  bannerCloseText: { color: "#444", fontSize: 13 },

  header: { paddingTop: 8, gap: 10 },
  headerBadge: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: "rgba(255,255,255,0.05)", borderWidth: 1, borderColor: "rgba(255,255,255,0.1)", borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 },
  headerDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#22c55e" },
  headerBadgeText: { color: "#888", fontSize: 11 },
  title: { color: "#fff", fontSize: 36, fontWeight: "800", letterSpacing: -1, lineHeight: 42 },
  subtitle: { color: "#555", fontSize: 14, lineHeight: 20 },

  scanBtn: {
    backgroundColor: "#6366f1",
    borderRadius: 18, padding: 18,
    flexDirection: "row", alignItems: "center", gap: 14,
    shadowColor: "#6366f1", shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4, shadowRadius: 16, elevation: 8,
  },
  scanBtnLoading: { backgroundColor: "#3730a3" },
  scanIcon: { fontSize: 28 },
  scanText: { color: "#fff", fontSize: 17, fontWeight: "700" },
  scanSub: { color: "rgba(255,255,255,0.6)", fontSize: 12, marginTop: 2 },

  manualCard: { backgroundColor: "#0e0e1a", borderRadius: 16, padding: 16, borderWidth: 1, borderColor: "rgba(255,255,255,0.06)", gap: 10 },
  manualLabel: { color: "#666", fontSize: 12, fontWeight: "600", letterSpacing: 0.5 },
  manualRow: { flexDirection: "row", gap: 8 },
  manualInput: { flex: 1, backgroundColor: "#161624", color: "#fff", borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, borderWidth: 1, borderColor: "rgba(255,255,255,0.08)" },
  manualBtn: { backgroundColor: "#6366f1", borderRadius: 10, paddingHorizontal: 18, alignItems: "center", justifyContent: "center" },
  manualBtnDisabled: { backgroundColor: "#2d2d4a" },
  manualBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },

  card: { backgroundColor: "#0e0e1a", borderRadius: 16, padding: 16, borderWidth: 1, borderColor: "rgba(255,255,255,0.06)", gap: 10 },
  cardTitle: { color: "#fff", fontWeight: "700", fontSize: 14, marginBottom: 4 },

  chipGrid: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  chip: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: "rgba(255,255,255,0.05)", borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: "rgba(255,255,255,0.08)" },
  chipIcon: { fontSize: 12 },
  chipText: { color: "#aaa", fontSize: 11, fontWeight: "600" },

  stepRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  stepNum: { width: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(99,102,241,0.15)", borderWidth: 1, borderColor: "rgba(99,102,241,0.3)", alignItems: "center", justifyContent: "center", marginTop: 1 },
  stepNumText: { color: "#818cf8", fontSize: 11, fontWeight: "700" },
  stepText: { color: "#888", fontSize: 13, flex: 1, lineHeight: 20 },

  sectionTitle: { color: "#333", fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  historyRow: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#0e0e1a", borderRadius: 12, padding: 12, borderWidth: 1, borderColor: "rgba(255,255,255,0.05)", marginBottom: 6 },
  historyDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  historyInfo: { flex: 1, gap: 2 },
  historyTitle: { color: "#ddd", fontSize: 13, fontWeight: "600" },
  historyUrl: { color: "#444", fontSize: 11 },
  historyPlatform: { color: "#333", fontSize: 10 },
  historyRight: { alignItems: "flex-end", gap: 2 },
  historyPct: { fontSize: 15, fontWeight: "800" },
  historyTime: { color: "#333", fontSize: 10 },

  empty: { alignItems: "center", paddingVertical: 60, gap: 8 },
  emptyIcon: { fontSize: 44 },
  emptyText: { color: "#333", fontSize: 16, fontWeight: "600" },
  emptySub: { color: "#222", fontSize: 13 },
});
