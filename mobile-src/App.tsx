/**
 * Main app entry point.
 *
 * Two flows:
 * 1. Share Extension (iOS + Android): user shares video → app opens → detects
 * 2. Floating Button (Android only): button overlays any app → tap → reads clipboard URL → detects
 */
import React, { useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  StatusBar,
  ScrollView,
  TouchableOpacity,
  Platform,
  Alert,
} from "react-native";
import { DetectionResult, detectVideoFile, detectVideoUrl } from "./services/detector";
import { ResultOverlay } from "./components/ResultOverlay";
import { FloatingButton } from "./components/FloatingButton";
import { useShareExtension } from "./hooks/useShareExtension";
import { useClipboardDetect } from "./hooks/useClipboardDetect";

type HistoryItem = DetectionResult & { timestamp: Date; source: string };

export default function App() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const { getVideoUrlFromClipboard } = useClipboardDetect();

  const handleResult = useCallback((r: DetectionResult, source: string) => {
    setResult(r);
    setHistory((prev) => [{ ...r, timestamp: new Date(), source }, ...prev.slice(0, 19)]);
  }, []);

  const runDetection = useCallback(async (action: () => Promise<DetectionResult>, source: string) => {
    setLoading(true);
    setResult(null);
    try {
      const r = await action();
      handleResult(r, source);
    } catch (e: unknown) {
      Alert.alert("Detection Failed", e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [handleResult]);

  // iOS Share Extension + Android Share Intent
  useShareExtension(
    useCallback((item) => {
      if (item.type === "url") {
        runDetection(() => detectVideoUrl(item.value), item.value);
      } else {
        runDetection(() => detectVideoFile(item.uri, item.filename), item.filename);
      }
    }, [runDetection])
  );

  // Android floating button → clipboard
  const onFloatingPress = useCallback(async () => {
    const url = await getVideoUrlFromClipboard();
    if (url) {
      runDetection(() => detectVideoUrl(url), url);
    } else {
      Alert.alert(
        "No video URL found",
        "Copy a video link first (Share → Copy Link), then tap the button.",
        [{ text: "OK" }]
      );
    }
  }, [getVideoUrlFromClipboard, runDetection]);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor="#07070f" />

      {/* Result overlay — appears when detection finishes */}
      {result && (
        <ResultOverlay result={result} onClose={() => setResult(null)} />
      )}

      {/* Android floating button */}
      <FloatingButton onPress={onFloatingPress} loading={loading} />

      {/* Main screen */}
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.title}>AI Video Detector</Text>
          <Text style={styles.subtitle}>
            {Platform.OS === "ios"
              ? "Share any video here to detect if it's AI-generated"
              : "Tap the floating button after copying a video link"}
          </Text>
        </View>

        {/* How to use card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>
            {Platform.OS === "ios" ? "📱 How to use on iOS" : "📱 How to use on Android"}
          </Text>
          {Platform.OS === "ios" ? (
            <>
              <Step n={1} text="Open TikTok, Reels, or YouTube" />
              <Step n={2} text="Tap Share on any video" />
              <Step n={3} text='Select "AI Detector" from the share sheet' />
              <Step n={4} text="Result appears in seconds" />
            </>
          ) : (
            <>
              <Step n={1} text="Open TikTok, Reels, or YouTube" />
              <Step n={2} text="Tap Share → Copy Link on any video" />
              <Step n={3} text="Tap the floating 🔍 button" />
              <Step n={4} text="Result appears as an overlay" />
            </>
          )}
        </View>

        {/* History */}
        {history.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Recent Detections</Text>
            {history.map((item, i) => (
              <HistoryRow key={i} item={item} />
            ))}
          </View>
        )}

        {history.length === 0 && (
          <View style={styles.emptyState}>
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

function HistoryRow({ item }: { item: HistoryItem }) {
  const isAI = item.is_ai_generated;
  const color = isAI ? "#f97316" : "#22c55e";
  const pct = Math.round(item.confidence * 100);
  return (
    <View style={styles.historyRow}>
      <View style={[styles.historyDot, { backgroundColor: color }]} />
      <View style={styles.historyInfo}>
        <Text style={styles.historyTitle} numberOfLines={1}>
          {isAI ? (item.ai_tool_detected ? `AI · ${item.ai_tool_detected}` : "AI Generated") : "Authentic"}
        </Text>
        <Text style={styles.historySource} numberOfLines={1}>{item.source}</Text>
      </View>
      <Text style={[styles.historyPct, { color }]}>{pct}%</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#07070f" },
  scroll: { padding: 20, gap: 16, paddingBottom: 40 },
  header: { paddingTop: 12, paddingBottom: 8, gap: 8 },
  title: { color: "#fff", fontSize: 28, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { color: "#666", fontSize: 15, lineHeight: 22 },

  card: {
    backgroundColor: "#0e0e1a",
    borderRadius: 16,
    padding: 18,
    borderWidth: 1,
    borderColor: "#ffffff0f",
    gap: 12,
  },
  cardTitle: { color: "#fff", fontWeight: "700", fontSize: 15, marginBottom: 4 },

  step: { flexDirection: "row", alignItems: "center", gap: 12 },
  stepNum: {
    width: 26, height: 26, borderRadius: 13,
    backgroundColor: "#6366f120",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "#6366f155",
  },
  stepNumText: { color: "#818cf8", fontSize: 12, fontWeight: "700" },
  stepText: { color: "#aaa", fontSize: 14, flex: 1 },

  section: { gap: 8 },
  sectionTitle: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 },

  historyRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#0e0e1a",
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: "#ffffff08",
  },
  historyDot: { width: 8, height: 8, borderRadius: 4 },
  historyInfo: { flex: 1, gap: 2 },
  historyTitle: { color: "#ddd", fontSize: 14, fontWeight: "600" },
  historySource: { color: "#555", fontSize: 11 },
  historyPct: { fontSize: 16, fontWeight: "800" },

  emptyState: { alignItems: "center", paddingVertical: 60, gap: 8 },
  emptyIcon: { fontSize: 48 },
  emptyText: { color: "#444", fontSize: 15 },
});
