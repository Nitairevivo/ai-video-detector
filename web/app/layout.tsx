import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  metadataBase: new URL("https://verifai.app"),
  title: "VerifAI — Is this video real or AI?",
  description:
    "Detect AI-generated videos (Sora, Veo, Kling, Runway…) — cryptographic C2PA verification, platform AI labels and a calibrated vision ensemble. Videos deleted right after analysis.",
  keywords: ["AI video detector", "deepfake detection", "C2PA", "content credentials", "Sora", "AI generated"],
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
      <body className="min-h-full bg-[#060314] text-white">{children}</body>
    </html>
  );
}
