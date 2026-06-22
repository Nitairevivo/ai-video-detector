import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  Animated,
  Pressable,
  Dimensions,
} from "react-native";
import { DetectionResult } from "../services/detector";

const { width } = Dimensions.get("window");

type Props = {
  result: DetectionResult;
  onClose: () => void;
};

export function ResultOverlay({ result, onClose }: Props) {
  const slideAnim = useRef(new Animated.Value(-200)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true, tension: 80, friction: 9 }),
      Animated.timing(opacityAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();

    const timer = setTimeout(onClose, 6000);
    return () => clearTimeout(timer);
  }, []);

  const isAI = result.is_ai_generated;
  const pct = Math.round(result.confidence * 100);
  const color = isAI ? "#ff4444" : "#22c55e";
  const bg = isAI ? "#1a0505" : "#031a0a";

  return (
    <Animated.View
      style={[
        styles.container,
        { transform: [{ translateY: slideAnim }], opacity: opacityAnim },
      ]}
    >
      <View style={[styles.card, { backgroundColor: bg, borderColor: color + "55" }]}>
        {/* Color bar at top */}
        <View style={[styles.topBar, { backgroundColor: color }]} />

        <View style={styles.content}>
          {/* Verdict badge */}
          <View style={[styles.badge, { backgroundColor: color + "22" }]}>
            <View style={[styles.dot, { backgroundColor: color }]} />
            <Text style={[styles.badgeText, { color }]}>
              {isAI ? "AI GENERATED" : "AUTHENTIC"}
            </Text>
          </View>

          {/* Main info */}
          <View style={styles.row}>
            <View style={styles.info}>
              <Text style={styles.title}>
                {isAI
                  ? result.ai_tool_detected
                    ? `Made with ${result.ai_tool_detected}`
                    : "AI-Generated Video"
                  : "Real footage"}
              </Text>
              <Text style={styles.method} numberOfLines={2}>
                {result.detection_method}
              </Text>
            </View>

            {/* Confidence circle */}
            <View style={[styles.circle, { borderColor: color }]}>
              <Text style={[styles.circleText, { color }]}>{pct}%</Text>
              <Text style={styles.circleLabel}>confidence</Text>
            </View>
          </View>
        </View>

        {/* Close */}
        <Pressable style={styles.closeBtn} onPress={onClose}>
          <Text style={styles.closeText}>✕</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    top: 60,
    left: 12,
    right: 12,
    zIndex: 9999,
  },
  card: {
    borderRadius: 16,
    borderWidth: 1,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 20,
  },
  topBar: {
    height: 3,
    width: "100%",
  },
  content: {
    padding: 14,
    gap: 10,
  },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 20,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  info: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  method: {
    color: "#888",
    fontSize: 12,
    lineHeight: 16,
  },
  circle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 2.5,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  circleText: {
    fontSize: 16,
    fontWeight: "800",
  },
  circleLabel: {
    color: "#666",
    fontSize: 8,
    marginTop: 1,
  },
  closeBtn: {
    position: "absolute",
    top: 12,
    right: 12,
    width: 24,
    height: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  closeText: {
    color: "#555",
    fontSize: 14,
  },
});
