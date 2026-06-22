/**
 * Android-only floating button that sits on top of all other apps.
 * Tapping it captures the current video URL from clipboard and sends
 * it to the API for analysis.
 *
 * On iOS this component renders nothing — use the Share Extension instead.
 */
import React, { useRef } from "react";
import {
  Platform,
  StyleSheet,
  Text,
  Animated,
  PanResponder,
  TouchableOpacity,
  View,
} from "react-native";

type Props = {
  onPress: () => void;
  loading: boolean;
};

export function FloatingButton({ onPress, loading }: Props) {
  if (Platform.OS !== "android") return null;

  const pan = useRef(new Animated.ValueXY({ x: 20, y: 120 })).current;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gesture) =>
        Math.abs(gesture.dx) > 4 || Math.abs(gesture.dy) > 4,
      onPanResponderMove: Animated.event([null, { dx: pan.x, dy: pan.y }], {
        useNativeDriver: false,
      }),
      onPanResponderRelease: () => {
        pan.extractOffset();
      },
    })
  ).current;

  return (
    <Animated.View
      style={[styles.container, { transform: pan.getTranslateTransform() }]}
      {...panResponder.panHandlers}
    >
      <TouchableOpacity
        style={[styles.button, loading && styles.buttonLoading]}
        onPress={onPress}
        activeOpacity={0.85}
      >
        {loading ? (
          <Text style={styles.icon}>⏳</Text>
        ) : (
          <>
            <Text style={styles.icon}>🔍</Text>
            <Text style={styles.label}>AI?</Text>
          </>
        )}
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    zIndex: 9999,
  },
  button: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: "#6366f1",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#6366f1",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.5,
    shadowRadius: 12,
    elevation: 12,
    gap: 1,
  },
  buttonLoading: {
    backgroundColor: "#4b5563",
  },
  icon: {
    fontSize: 20,
  },
  label: {
    color: "#fff",
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
});
