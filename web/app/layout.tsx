import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const viewport: Viewport = {
  themeColor: "#060314",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover", // fill under the iPhone notch / home indicator
};

export const metadata: Metadata = {
  metadataBase: new URL("https://verifai.app"),
  title: "VerifAI — Is this video real or AI?",
  description:
    "Detect AI-generated videos (Sora, Veo, Kling, Runway…) — cryptographic C2PA verification, platform AI labels and a calibrated vision ensemble. Videos deleted right after analysis.",
  keywords: ["AI video detector", "deepfake detection", "C2PA", "content credentials", "Sora", "AI generated"],
  // Installable to the iPhone/Android home screen — no app store, no Apple ID.
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "VerifAI",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: "/icon.svg",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "VerifAI — Is this video real or AI?",
    description:
      "Reads the evidence platforms can't erase: C2PA credentials, platform AI labels, and a calibrated vision ensemble.",
    type: "website",
    siteName: "VerifAI",
  },
  twitter: {
    card: "summary_large_image",
    title: "VerifAI — Is this video real or AI?",
    description: "Detect AI-generated videos in seconds. Privacy safe — videos deleted right after analysis.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-[#060314] text-white">
        {/* Always offer the REAL native Android app (the APK), on every page —
            not a PWA/web shortcut. Slim, sticky, one tap to download. */}
        <a
          href="https://github.com/Nitairevivo/ai-video-detector/releases/tag/apk-latest"
          dir="rtl"
          className="sticky top-0 z-50 flex items-center justify-center gap-2 px-4 py-2 text-[13px] font-bold text-black no-underline"
          style={{ background: "linear-gradient(135deg,#5eead4,#2fe0a4)" }}
        >
          <span aria-hidden="true">📱</span>
          קבל את אפליקציית VerifAI לאנדרואיד — הורדה חינם
          <span aria-hidden="true">›</span>
        </a>
        {children}
      </body>
    </html>
  );
}
