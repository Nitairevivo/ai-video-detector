/**
 * Android floating button flow:
 * When the user taps the floating button, we read the clipboard.
 * TikTok, Instagram, YouTube all copy the video URL when you tap "Share → Copy Link".
 * We send that URL directly to /detect-url.
 */
import { useCallback } from "react";
import { Clipboard, Alert, Platform } from "react-native";

const VIDEO_URL_PATTERNS = [
  /tiktok\.com/,
  /instagram\.com\/reel/,
  /instagram\.com\/p\//,
  /youtube\.com\/shorts/,
  /youtu\.be/,
  /twitter\.com\/.*\/video/,
  /x\.com\/.*\/video/,
  /reddit\.com\/.*\/v\//,
];

export function useClipboardDetect() {
  const getVideoUrlFromClipboard = useCallback(async (): Promise<string | null> => {
    try {
      const text = await Clipboard.getString();
      if (!text?.startsWith("http")) return null;

      const isVideoUrl = VIDEO_URL_PATTERNS.some((p) => p.test(text));
      if (isVideoUrl) return text;

      // Ask user if URL looks like a video
      return new Promise((resolve) => {
        Alert.alert(
          "Clipboard URL",
          `Analyze this URL?\n\n${text.slice(0, 80)}...`,
          [
            { text: "Cancel", onPress: () => resolve(null), style: "cancel" },
            { text: "Analyze", onPress: () => resolve(text) },
          ]
        );
      });
    } catch {
      return null;
    }
  }, []);

  return { getVideoUrlFromClipboard };
}
