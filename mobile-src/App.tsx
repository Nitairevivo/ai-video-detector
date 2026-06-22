"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  View, Text, StyleSheet, Animated, TouchableOpacity,
  Platform, SafeAreaView, StatusBar, ScrollView,
  Clipboard, Alert, Linking, AppState, Vibration,
} from "react-native";

const API = "https://ai-video-detector-production-a305.up.railway.app";

type Result = {
  is_ai_generated: boolean;
  confidence: number;
  ai_tool_detected: string | null;
  detection_method: string;
};

type HistoryItem = Result & { timestamp: string; url: string };

// ─── Overlay Result Banner ────────────────────────────────────────────────────

function ResultBanner({ result, onDismiss }: { result: Result; onDismiss: () => void }) {
  const slideY = useRef(new Animated.Value(-120)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideY, { toValue: 0, useNativeDriver: true, tension: 70, friction: 10 }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
    const t = setTimeout(onDismiss, 7000);
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

// ─── Floating Button (Android only) ──────────────────────────────────────────

function FloatingBtn({ onPress, loading }: { onPress: () => void; loading: boolean }) {
  if (Platform.OS !== "android") return null;
  const scale = useRef(new Animated.Value(1)).current;

  const press = () => {
    Animated.sequence([
      Animated.timing(scale, { toValue: 0.9, duration: 80, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, useNativeDriver: true }),
    ]).start();
    onPress();
  };

  return (
    <Animated.View style={[styles.fab, { transform: [{ scale }] }]}>
      <TouchableOpacity style={[styles.fabBtn, loading && styles.fabLoading]} onPress={press} activeOpacity={0.85}>
        <Text style={styles.fabIcon}>{loading ? "⏳" : "🔍"}</Text>
        {!loading && <Text style={styles.fabLabel}>AI?</Text>}
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

  // Auto-check clipboard when app comes to foreground (Android)
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const sub = AppState.addEventListener("change", async (state) => {
      if (state !== "active") return;
      try {
        const text = await Clipboard.getString();
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
      setResult(data);
      setHistory(prev => [{ ...data, timestamp: new Date().toLocaleTimeString(), url }, ...prev.slice(0, 29)]);
      Vibration.vibrate(data.is_ai_generated ? [0, 80, 60, 80] : 50);
    } catch (e: unknown) {
      Alert.alert("Detection Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const onFloatingPress = useCallback(async () => {
    try {
      const text = await Clipboard.getString();
      if (!text?.startsWith("http")) {
        Alert.alert("No URL found", "In TikTok/Reels:\n1. Tap Share\n2. Tap Copy Link\n3. Come back and tap the button");
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

      {/* Result overlay */}
      {result && <ResultBanner result={result} onDismiss={() => setResult(null)} />}

      {/* Floating button — Android only */}
      <FloatingBtn onPress={onFloatingPress} loading={loading} />

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>AI Video{"\n"}Detector</Text>
          <Text style={styles.subtitle}>
            {Platform.OS === "android"
              ? "Copy a video link in TikTok/Reels, then tap 🔍"
              : "Share any video to this app to detect if it's AI"}
          </Text>
        </View>

        {/* How to use */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>
            {Platform.OS === "android" ? "📱 Android — How to use" : "📱 iOS — How to use"}
          </Text>
          {Platform.OS === "android" ? (
            <>
              <Step n={1} text="Open TikTok, Instagram or YouTube" />
              <Step n={2} text='Tap Share → "Copy Link" on any video' />
              <Step n={3} text="Switch back here or tap 🔍 button" />
              <Step n={4} text="Result appears in 2-3 seconds" />
            </>
          ) : (
            <>
              <Step n={1} text="Open TikTok, Reels or YouTube" />
              <Step n={2} text="Tap Share on any video" />
              <Step n={3} text='Select "AI Detector" from the list' />
              <Step n={4} text="Result appears instantly" />
            </>
          )}
        </View>

        {/* History */}
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
                      ? (item.ai_tool_detected ? `AI · ${item.ai_tool_detected}` : "AI Generated")
                      : "Authentic Footage"}
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

function isVideoUrl(url: string): boolean {
  return /tiktok\.com|instagram\.com\/(reel|p\/)|youtube\.com\/shorts|youtu\.be|twitter\.com.*video|x\.com.*video|reddit\.com.*comments/i.test(url);
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#07070f" },
  scroll: { padding: 20, paddingBottom: 120, gap: 16 },

  // Banner
  banner: {
    position: "absolute", top: 50, left: 12, right: 12,
    zIndex: 9999, borderRadius: 16, borderWidth: 1,
    overflow: "hidden",
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
  bannerPct: { fontSize: 16, fontWeight: "800" },
  bannerConf: { color: "#555", fontSize: 8 },
  bannerClose: { position: "absolute", top: 10, right: 10, padding: 4 },
  bannerCloseText: { color: "#444", fontSize: 13 },

  // FAB
  fab: { position: "absolute", bottom: 40, right: 24, zIndex: 9998 },
  fabBtn: {
    width: 62, height: 62, borderRadius: 31,
    backgroundColor: "#6366f1", alignItems: "center", justifyContent: "center",
    shadowColor: "#6366f1", shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.6, shadowRadius: 14, elevation: 14,
  },
  fabLoading: { backgroundColor: "#374151" },
  fabIcon: { fontSize: 22 },
  fabLabel: { color: "#fff", fontSize: 8, fontWeight: "800", letterSpacing: 0.5 },

  // Main
  header: { paddingTop: 8, gap: 8 },
  title: { color: "#fff", fontSize: 34, fontWeight: "800", letterSpacing: -0.5, lineHeight: 40 },
  subtitle: { color: "#555", fontSize: 14, lineHeight: 20 },

  card: { backgroundColor: "#0e0e1a", borderRadius: 16, padding: 16, borderWidth: 1, borderColor: "#ffffff0f", gap: 10 },
  cardTitle: { color: "#ddd", fontWeight: "700", fontSize: 14, marginBottom: 2 },

  step: { flexDirection: "row", alignItems: "center", gap: 10 },
  stepNum: { width: 24, height: 24, borderRadius: 12, backgroundColor: "#6366f115", borderWidth: 1, borderColor: "#6366f140", alignItems: "center", justifyContent: "center" },
  stepNumText: { color: "#818cf8", fontSize: 11, fontWeight: "700" },
  stepText: { color: "#888", fontSize: 13, flex: 1 },

  section: { gap: 8 },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sectionTitle: { color: "#444", fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  clearBtn: { color: "#444", fontSize: 11 },

  historyRow: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#0e0e1a", borderRadius: 12, padding: 12, borderWidth: 1, borderColor: "#ffffff08" },
  historyDot: { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  historyInfo: { flex: 1, gap: 2 },
  historyTitle: { color: "#ccc", fontSize: 13, fontWeight: "600" },
  historyUrl: { color: "#444", fontSize: 10 },
  historyPct: { fontSize: 15, fontWeight: "800" },

  empty: { alignItems: "center", paddingVertical: 60, gap: 8 },
  emptyIcon: { fontSize: 44 },
  emptyText: { color: "#333", fontSize: 14 },
});
