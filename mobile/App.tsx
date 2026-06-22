import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  View, Text, StyleSheet, Animated, TouchableOpacity,
  SafeAreaView, StatusBar, ScrollView, Alert, Vibration,
  AppState, Platform,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import { useShareIntent } from "expo-share-intent";

const API = "https://ai-video-detector-production-a305.up.railway.app";

type Result = {
  is_ai_generated: boolean;
  confidence: number;
  ai_tool_detected: string | null;
  detection_method: string;
  url?: string;
};

type HistoryItem = Result & { timestamp: string; url: string };

const VIDEO_URL_PATTERNS = [
  /tiktok\.com/,
  /instagram\.com\/(reel|p|tv)\//,
  /youtube\.com\/(shorts|watch|live)/,
  /youtu\.be\//,
  /twitter\.com\/.*\/status/,
  /x\.com\/.*\/status/,
  /reddit\.com\/r\/.*\/comments/,
  /v\.redd\.it\//,
  /facebook\.com\/(watch|reel|videos)/,
  /fb\.watch\//,
  /t\.me\//,
];

function isVideoUrl(url: string) {
  return VIDEO_URL_PATTERNS.some((p) => p.test(url));
}

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
              {isAI ? "🤖 AI GENERATED" : "✅ AUTHENTIC"}
            </Text>
          </View>
          <Text style={styles.bannerTitle}>
            {isAI
              ? (result.ai_tool_detected ? `Made with ${result.ai_tool_detected}` : "AI-Generated Video")
              : "Real Footage"}
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

// ─── Floating Button ──────────────────────────────────────────────────────────

function FloatingBtn({ onPress, loading }: { onPress: () => void; loading: boolean }) {
  const scale = useRef(new Animated.Value(1)).current;
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (loading) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.15, duration: 600, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulse.stopAnimation();
      pulse.setValue(1);
    }
  }, [loading]);

  const press = () => {
    Animated.sequence([
      Animated.timing(scale, { toValue: 0.88, duration: 80, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, useNativeDriver: true }),
    ]).start();
    onPress();
  };

  return (
    <Animated.View style={[styles.fab, { transform: [{ scale: Animated.multiply(scale, pulse) }] }]}>
      <TouchableOpacity style={[styles.fabBtn, loading && styles.fabLoading]} onPress={press} activeOpacity={0.85}>
        <Text style={styles.fabIcon}>{loading ? "⏳" : "🔍"}</Text>
        {!loading && <Text style={styles.fabLabel}>CHECK</Text>}
      </TouchableOpacity>
    </Animated.View>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const lastChecked = useRef<string>("");

  // iOS Share Extension: receives URL when user shares from TikTok/Reels/YouTube
  const { shareIntent, resetShareIntent, hasShareIntent } = useShareIntent();

  useEffect(() => {
    if (!hasShareIntent) return;
    const url = shareIntent?.webUrl || shareIntent?.text;
    if (url && url.startsWith("http")) {
      resetShareIntent();
      detect(url);
    }
  }, [hasShareIntent, shareIntent]);

  // Android: auto-detect clipboard on app focus
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
    try {
      const res = await fetch(`${API}/detect-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data: Result = await res.json();
      const item = { ...data, timestamp: new Date().toLocaleTimeString(), url };
      setResult(item);
      setHistory(prev => [item, ...prev.slice(0, 29)]);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch (e: unknown) {
      Alert.alert("Detection Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const onFloatingPress = useCallback(async () => {
    try {
      const text = await Clipboard.getStringAsync();
      if (!text?.startsWith("http")) {
        Alert.alert(
          "Copy a link first",
          "In TikTok:\n1. Tap Share on a video\n2. Tap 'Copy Link'\n3. Come back and tap 🔍\n\nOn iOS you can also use the Share Sheet directly.",
          [{ text: "OK" }]
        );
        return;
      }
      if (!isVideoUrl(text)) {
        Alert.alert("Analyze this URL?", text.slice(0, 100), [
          { text: "Cancel", style: "cancel" },
          { text: "Analyze", onPress: () => detect(text) },
        ]);
        return;
      }
      detect(text);
    } catch {
      Alert.alert("Error", "Could not read clipboard");
    }
  }, [detect]);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor="#07070f" />

      {result && <ResultBanner result={result} onDismiss={() => setResult(null)} />}
      <FloatingBtn onPress={onFloatingPress} loading={loading} />

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.titleSmall}>AI VIDEO</Text>
          <Text style={styles.title}>DETECTOR</Text>
          <Text style={styles.subtitle}>
            {Platform.OS === "ios"
              ? "Share any video from TikTok, Reels or YouTube directly to this app"
              : "Copy a TikTok/Reels link, then tap 🔍 below"}
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>
            {Platform.OS === "ios" ? "📱 How to use on iOS" : "📱 How to use on Android"}
          </Text>
          {Platform.OS === "ios" ? (
            <>
              <Step n={1} text="Open TikTok, Instagram or YouTube" />
              <Step n={2} text="Tap Share on any video" />
              <Step n={3} text='Select "AI Detector" from the share sheet' />
              <Step n={4} text="Result appears here in 2–3 seconds" />
            </>
          ) : (
            <>
              <Step n={1} text="Open TikTok, Instagram or YouTube" />
              <Step n={2} text='Tap Share → "Copy Link"' />
              <Step n={3} text="Switch back here and tap 🔍" />
              <Step n={4} text="Result appears in 2–3 seconds" />
            </>
          )}
        </View>

        {history.length > 0 && (
          <View style={styles.section}>
            <View style={styles.sectionRow}>
              <Text style={styles.sectionTitle}>RECENT</Text>
              <TouchableOpacity onPress={() => setHistory([])}>
                <Text style={styles.clearBtn}>Clear</Text>
              </TouchableOpacity>
            </View>
            {history.map((item, i) => (
              <TouchableOpacity key={i} style={styles.historyRow} onPress={() => setResult(item)}>
                <View style={[styles.historyDot, { backgroundColor: item.is_ai_generated ? "#ef4444" : "#22c55e" }]} />
                <View style={styles.historyInfo}>
                  <Text style={styles.historyTitle}>
                    {item.is_ai_generated
                      ? (item.ai_tool_detected ? `🤖 AI · ${item.ai_tool_detected}` : "🤖 AI Generated")
                      : "✅ Authentic Footage"}
                  </Text>
                  <Text style={styles.historyUrl} numberOfLines={1}>{item.url}</Text>
                </View>
                <Text style={[styles.historyPct, { color: item.is_ai_generated ? "#ef4444" : "#22c55e" }]}>
                  {Math.round(item.confidence * 100)}%
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {history.length === 0 && (
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>🎬</Text>
            <Text style={styles.emptyText}>No videos analyzed yet</Text>
            <Text style={styles.emptyHint}>
              {Platform.OS === "ios"
                ? "Share a video from TikTok to get started"
                : "Copy a TikTok link and tap 🔍"}
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Step({ n, text }: { n: number; text: string }) {
  return (
    <View style={styles.step}>
      <View style={styles.stepNum}>
        <Text style={styles.stepNumText}>{n}</Text>
      </View>
      <Text style={styles.stepText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#07070f" },
  scroll: { padding: 20, paddingBottom: 140, gap: 20 },

  banner: {
    position: "absolute", top: 50, left: 12, right: 12,
    zIndex: 9999, borderRadius: 18, borderWidth: 1, overflow: "hidden",
    shadowColor: "#000", shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.6, shadowRadius: 24, elevation: 24,
  },
  bannerBar: { height: 3 },
  bannerBody: { flexDirection: "row", alignItems: "center", padding: 16, gap: 12 },
  bannerLeft: { flex: 1, gap: 5 },
  bannerBadge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  bannerDot: { width: 5, height: 5, borderRadius: 3 },
  bannerBadgeText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.8 },
  bannerTitle: { color: "#fff", fontSize: 16, fontWeight: "700" },
  bannerMethod: { color: "#555", fontSize: 11 },
  bannerCircle: { width: 64, height: 64, borderRadius: 32, borderWidth: 2.5, alignItems: "center", justifyContent: "center" },
  bannerPct: { fontSize: 18, fontWeight: "800" },
  bannerConf: { color: "#555", fontSize: 8 },
  bannerClose: { position: "absolute", top: 10, right: 12, padding: 6 },
  bannerCloseText: { color: "#444", fontSize: 14 },

  fab: { position: "absolute", bottom: 44, right: 24, zIndex: 9998 },
  fabBtn: {
    width: 68, height: 68, borderRadius: 34,
    backgroundColor: "#6366f1", alignItems: "center", justifyContent: "center",
    shadowColor: "#6366f1", shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.7, shadowRadius: 16, elevation: 16,
  },
  fabLoading: { backgroundColor: "#2a2a3a" },
  fabIcon: { fontSize: 24 },
  fabLabel: { color: "#fff", fontSize: 8, fontWeight: "800", letterSpacing: 1 },

  header: { paddingTop: 8, gap: 4 },
  titleSmall: { color: "#6366f1", fontSize: 12, fontWeight: "800", letterSpacing: 4 },
  title: { color: "#fff", fontSize: 38, fontWeight: "900", letterSpacing: -1 },
  subtitle: { color: "#555", fontSize: 14, lineHeight: 20, marginTop: 4 },

  card: { backgroundColor: "#0d0d1a", borderRadius: 18, padding: 18, borderWidth: 1, borderColor: "#ffffff0a", gap: 12 },
  cardTitle: { color: "#ccc", fontWeight: "700", fontSize: 14, marginBottom: 2 },

  step: { flexDirection: "row", alignItems: "center", gap: 12 },
  stepNum: { width: 26, height: 26, borderRadius: 13, backgroundColor: "#6366f115", borderWidth: 1, borderColor: "#6366f140", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  stepNumText: { color: "#818cf8", fontSize: 12, fontWeight: "700" },
  stepText: { color: "#888", fontSize: 13, flex: 1, lineHeight: 18 },

  section: { gap: 10 },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sectionTitle: { color: "#444", fontSize: 10, fontWeight: "700", letterSpacing: 1.5 },
  clearBtn: { color: "#444", fontSize: 12 },

  historyRow: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#0d0d1a", borderRadius: 14, padding: 14, borderWidth: 1, borderColor: "#ffffff08" },
  historyDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  historyInfo: { flex: 1, gap: 3 },
  historyTitle: { color: "#ccc", fontSize: 13, fontWeight: "600" },
  historyUrl: { color: "#444", fontSize: 10 },
  historyPct: { fontSize: 16, fontWeight: "800" },

  empty: { alignItems: "center", paddingVertical: 60, gap: 10 },
  emptyIcon: { fontSize: 48 },
  emptyText: { color: "#444", fontSize: 15, fontWeight: "600" },
  emptyHint: { color: "#333", fontSize: 12, textAlign: "center", lineHeight: 18 },
});
