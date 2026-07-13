import { ImageResponse } from "next/og";

export const alt = "VerifAI — Is this video real or AI?";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Bold, high-contrast social card. Rendered by next/og at build time.
export default function OG() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background:
            "radial-gradient(1000px 600px at 15% -10%, #2a0e63 0%, transparent 60%), radial-gradient(900px 600px at 100% 110%, #4a0f6b 0%, transparent 55%), #060314",
          fontFamily: "sans-serif",
          position: "relative",
        }}
      >
        {/* brand row */}
        <div style={{ display: "flex", alignItems: "center", gap: 22, marginBottom: 30 }}>
          <div
            style={{
              width: 84,
              height: 84,
              borderRadius: 24,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "linear-gradient(135deg, #7c3aed, #d946ef 55%, #22d3ee)",
              boxShadow: "0 20px 60px -10px rgba(217,70,239,0.6)",
            }}
          >
            <svg width="52" height="52" viewBox="0 0 40 40" fill="none">
              <path d="M11 20.5 L17.5 27.5 L29.5 12" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div style={{ display: "flex", fontSize: 46, fontWeight: 800, color: "white", letterSpacing: -1 }}>
            Verif<span style={{ color: "#e6a8ff" }}>AI</span>
          </div>
        </div>

        {/* headline */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 88, fontWeight: 900, color: "white", letterSpacing: -4, lineHeight: 1.16 }}>
            Is it real,
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 88,
              fontWeight: 900,
              letterSpacing: -4,
              lineHeight: 1.16,
              backgroundImage: "linear-gradient(110deg, #a855f7, #ff3ec9 55%, #22e3ee)",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            or is it AI?
          </div>
        </div>

        {/* sub */}
        <div style={{ display: "flex", fontSize: 31, color: "#a29dc4", marginTop: 30 }}>
          Reads the evidence platforms can&apos;t erase.
        </div>

        {/* verdict chips */}
        <div style={{ display: "flex", gap: 16, marginTop: 36 }}>
          {[
            ["🤖 AI Generated", "#ff3d6e"],
            ["✏️ AI Edited", "#c084fc"],
            ["✅ Authentic", "#2ee6a6"],
          ].map(([t, c]) => (
            <div
              key={t}
              style={{
                display: "flex",
                fontSize: 26,
                color: c,
                padding: "10px 24px",
                borderRadius: 999,
                border: `2px solid ${c}55`,
                background: `${c}18`,
              }}
            >
              {t}
            </div>
          ))}
        </div>
      </div>
    ),
    size
  );
}
