import type { MetadataRoute } from "next";

// Makes VerifAI installable to the iPhone/Android home screen straight from the
// browser — a real app icon + standalone (no browser chrome) — with NO app
// store, NO Apple Developer account, NO Apple ID. On iPhone: Safari → Share →
// "Add to Home Screen".
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "VerifAI — AI Video Detector",
    short_name: "VerifAI",
    description:
      "Is this video real or AI? Reads C2PA credentials, platform AI labels and a calibrated vision ensemble.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#060314",
    theme_color: "#060314",
    categories: ["utilities", "productivity"],
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
