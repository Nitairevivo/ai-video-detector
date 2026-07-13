"use client";

import { useEffect, useState } from "react";

// iPhone Safari never shows an install prompt — the user must tap Share → "Add
// to Home Screen". So on iPhone (and only when not already installed) we surface
// a small, dismissible hint that tells them exactly how. This is what turns the
// site into an installable app on iOS with no App Store and no Apple ID.
export default function IosInstallHint() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      const ua = window.navigator.userAgent || "";
      const isIOS = /iphone|ipad|ipod/i.test(ua);
      // Standalone = already added to home screen.
      const standalone =
        (window.navigator as unknown as { standalone?: boolean }).standalone ||
        window.matchMedia("(display-mode: standalone)").matches;
      const dismissed = localStorage.getItem("verifai_ios_hint") === "1";
      if (isIOS && !standalone && !dismissed) setShow(true);
    } catch {}
  }, []);

  if (!show) return null;

  return (
    <div
      className="fixed bottom-4 left-3 right-3 z-[60] mx-auto max-w-md rounded-2xl p-4 glass gborder"
      style={{ boxShadow: "0 20px 60px -12px rgba(217,70,239,0.5)" }}
    >
      <div className="flex items-start gap-3">
        <div className="text-2xl">📲</div>
        <div className="flex-1">
          <p className="text-white font-bold text-sm">Install VerifAI on your iPhone</p>
          <p className="text-muted text-xs mt-1 leading-relaxed">
            Tap <span className="text-white font-semibold">Share</span>{" "}
            <span className="inline-block align-middle" aria-hidden>􀈂</span> below, then{" "}
            <span className="text-white font-semibold">&ldquo;Add to Home Screen&rdquo;</span>. No App
            Store, no account.
          </p>
        </div>
        <button
          onClick={() => {
            try { localStorage.setItem("verifai_ios_hint", "1"); } catch {}
            setShow(false);
          }}
          className="text-faint hover:text-white text-sm px-1"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
