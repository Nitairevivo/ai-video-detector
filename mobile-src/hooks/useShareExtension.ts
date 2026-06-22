/**
 * Handles incoming shared content from iOS Share Sheet and Android Share Intent.
 * When user shares a video/URL to this app from TikTok, Reels, YouTube, etc.
 * this hook picks it up and triggers detection.
 */
import { useEffect, useState } from "react";
import { Platform, NativeModules, NativeEventEmitter } from "react-native";

export type SharedItem =
  | { type: "url"; value: string }
  | { type: "file"; uri: string; filename: string };

export function useShareExtension(onReceive: (item: SharedItem) => void) {
  useEffect(() => {
    // react-native-share-menu integration
    const ShareMenu = NativeModules.ShareMenu;
    if (!ShareMenu) return;

    // Check if the app was opened via a share action
    ShareMenu.getSharedText?.((text: string) => {
      if (text) {
        if (text.startsWith("http")) {
          onReceive({ type: "url", value: text });
        }
      }
    });

    // Listen for shares while the app is already open
    const emitter = new NativeEventEmitter(ShareMenu);
    const sub = emitter.addListener("NewShareEvent", (data: { text?: string; weblink?: string; files?: string[] }) => {
      const url = data.weblink || data.text;
      if (url?.startsWith("http")) {
        onReceive({ type: "url", value: url });
      } else if (data.files?.length) {
        onReceive({
          type: "file",
          uri: data.files[0],
          filename: data.files[0].split("/").pop() ?? "video.mp4",
        });
      }
    });

    return () => sub.remove();
  }, [onReceive]);
}
