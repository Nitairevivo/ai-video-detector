import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "VerifAI — AI Video Detector",
  description: "Instantly detect AI-generated videos using file-level forensics. No frame decoding. No privacy risk.",
  openGraph: {
    title: "VerifAI — AI Video Detector",
    description: "Instantly detect AI-generated videos using file-level forensics.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-[#06060f] text-white">{children}</body>
    </html>
  );
}
