"use client";

import { useState, useRef, useCallback, KeyboardEvent } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://ai-video-detector-production-a305.up.railway.app";

type DetectionResult = {
  filename: string;
  is_ai_generated: boolean;
  confidence: number;
  ai_tool_detected: string | null;
  detection_method: string;
  signals: Record<string, number>;
  rule_based_confidence: number;
  ml_confidence: number | null;
};

type VideoItem = {
  id: string;
  file?: File;
  url?: string;
  label: string;
  status: "pending" | "analyzing" | "done" | "error";
  result?: DetectionResult;
  error?: string;
};

const SIGNAL_LABELS: Record<string, string> = {
  has_ai_metadata_tag: "AI Metadata Tag",
  has_c2pa: "C2PA Provenance",
  c2pa_is_ai: "C2PA → AI Confirmed",
  pts_uniformity: "Frame Timing Uniformity",
  pts_jitter_std: "Timing Jitter",
  keyframe_interval_std: "Keyframe Regularity",
  frame_size_cv: "Frame Size Consistency",
  codec_ai_score: "Codec AI Score",
  moov_before_mdat: "Container Order (AI pattern)",
  has_proprietary_box: "Proprietary AI Box",
  container_ai_score: "Container AI Score",
  audio_ai_score: "Audio Pattern Score",
  silence_ratio: "Silence Ratio",
  scene_change_rate: "Scene Change Rate",
};

// ── Logo ────────────────────────────────────────────────────────────────────
function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
      <rect width="36" height="36" rx="10" fill="url(#lg)" />
      {/* Eye shape */}
      <path d="M7 18C7 18 11.5 11 18 11C24.5 11 29 18 29 18C29 18 24.5 25 18 25C11.5 25 7 18 7 18Z"
        stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      {/* Pupil */}
      <circle cx="18" cy="18" r="3.5" fill="white" />
      {/* Scan line */}
      <line x1="14" y1="18" x2="22" y2="18" stroke="#818cf8" strokeWidth="1.2" strokeLinecap="round" />
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4f46e5" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ── Confidence ring ──────────────────────────────────────────────────────────
function ConfidenceMeter({ value, isAI }: { value: number; isAI: boolean }) {
  const pct = Math.round(value * 100);
  const color = isAI ? "#f97316" : "#4ade80";
  return (
    <div className="relative w-28 h-28 flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#1a1a2e" strokeWidth="8" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
          strokeLinecap="round" strokeDasharray={`${2.51 * pct} 251`}
          style={{ transition: "stroke-dasharray 1s ease" }} />
      </svg>
      <div className="text-center z-10">
        <div className="text-2xl font-bold" style={{ color }}>{pct}%</div>
        <div className="text-[10px] text-gray-500 mt-0.5">confidence</div>
      </div>
    </div>
  );
}

// ── Result card ──────────────────────────────────────────────────────────────
function ResultCard({ item, onRemove, onRetry }: { item: VideoItem; onRemove: () => void; onRetry?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const r = item.result;

  if (item.status === "analyzing") {
    return (
      <div className="bg-white/3 border border-white/8 rounded-2xl p-5 flex items-center gap-4 animate-pulse">
        <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-violet-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <div>
          <p className="text-white text-sm font-medium truncate max-w-xs">{item.label}</p>
          <p className="text-gray-500 text-xs mt-0.5">{item.file ? `Reading file… · ${(item.file.size / 1024 / 1024).toFixed(1)} MB` : "Fetching from URL…"}</p>
        </div>
      </div>
    );
  }

  if (item.status === "error") {
    return (
      <div className="bg-red-500/5 border border-red-500/20 rounded-2xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center flex-shrink-0 text-lg">⚠</div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium truncate">{item.label}</p>
          <p className="text-red-400 text-xs mt-0.5">{item.error}</p>
          {onRetry && (
            <button onClick={onRetry} className="text-xs text-violet-400 hover:text-violet-300 mt-1.5 transition-colors underline underline-offset-2">
              Try again
            </button>
          )}
        </div>
        <button onClick={onRemove} className="text-gray-600 hover:text-gray-400 text-sm px-2">✕</button>
      </div>
    );
  }

  if (!r) return null;
  const isAI = r.is_ai_generated;

  return (
    <div className={`border rounded-2xl overflow-hidden transition-all duration-300 ${
      isAI ? "bg-red-500/5 border-red-500/25" : "bg-green-500/5 border-green-500/25"
    }`}>
      <div className="p-5 flex items-center gap-4">
        <ConfidenceMeter value={r.confidence} isAI={isAI} />
        <div className="flex-1 min-w-0">
          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold mb-2 ${
            isAI ? "bg-red-500/20 text-red-300" : "bg-green-500/20 text-green-300"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isAI ? "bg-red-400" : "bg-green-400"}`} />
            {isAI ? "AI GENERATED" : "AUTHENTIC"}
          </div>
          <p className="text-white font-semibold text-sm truncate">
            {isAI ? (r.ai_tool_detected ? `Made with ${r.ai_tool_detected}` : "AI-Generated Video") : "Real Footage"}
          </p>
          <p className="text-gray-500 text-xs mt-0.5 truncate">{item.label}</p>
          <p className="text-gray-600 text-xs mt-1 truncate">{r.detection_method}</p>
          <button onClick={() => setExpanded(v => !v)}
            className="text-xs text-gray-600 hover:text-gray-400 mt-2 transition-colors">
            {expanded ? "Hide signals ↑" : "Show signals ↓"}
          </button>
        </div>
        <button onClick={onRemove} className="text-gray-700 hover:text-gray-400 text-sm px-1 flex-shrink-0">✕</button>
      </div>

      {expanded && (
        <div className="px-5 pb-5 border-t border-white/5 pt-4 space-y-1.5">
          {Object.entries(SIGNAL_LABELS).map(([key, label]) =>
            r.signals[key] !== undefined ? (
              <div key={key} className="flex justify-between items-center text-xs">
                <span className="text-gray-500">{label}</span>
                <span className={`font-mono font-semibold ${
                  (r.signals[key] === 1 || (r.signals[key] > 0.6 && r.signals[key] !== 0))
                    ? "text-orange-400" : "text-gray-400"
                }`}>
                  {r.signals[key] === 1 ? "✓ YES" : r.signals[key] === 0 ? "— NO" : r.signals[key].toFixed(3)}
                </span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

// ── How it works step ────────────────────────────────────────────────────────
function Step({ n, title, desc, icon }: { n: string; title: string; desc: string; icon: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: "12px" }}>
      <div style={{ width: 56, height: 56, borderRadius: 16, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>
        {icon}
      </div>
      <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(124,58,237,0.3)", border: "1px solid rgba(139,92,246,0.5)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: "#c4b5fd", fontWeight: 700 }}>
        {n}
      </div>
      <div>
        <p style={{ color: "#ffffff", fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{title}</p>
        <p style={{ color: "#9ca3af", fontSize: 13, lineHeight: 1.6 }}>{desc}</p>
      </div>
    </div>
  );
}

// ── Feature pill ─────────────────────────────────────────────────────────────
function Feature({ icon, text }: { icon: string; text: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 999, padding: "8px 16px", fontSize: 14, color: "#d1d5db" }}>
      <span>{icon}</span>
      <span>{text}</span>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦", x: "🐦",
  reddit: "🤖", facebook: "👤", telegram: "✈️", snapchat: "👻",
  pinterest: "📌", twitch: "🎮", vimeo: "🎬", dailymotion: "🎬",
};

function getPlatformLabel(url: string): string {
  try {
    const host = new URL(url).hostname.replace("www.", "");
    const name = host.split(".")[0];
    const icon = PLATFORM_ICONS[name] ?? "🔗";
    return `${icon} ${host}`;
  } catch {
    return url.slice(0, 60);
  }
}

export default function Home() {
  const [items, setItems] = useState<VideoItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const analyzeItem = useCallback(async (item: VideoItem) => {
    setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "analyzing" } : i));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90_000);
    try {
      let res: Response;
      if (item.url) {
        res = await fetch(`${API}/detect-url`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: item.url }),
          signal: controller.signal,
        });
      } else {
        const form = new FormData();
        form.append("file", item.file!);
        res = await fetch(`${API}/detect`, { method: "POST", body: form, signal: controller.signal });
      }
      clearTimeout(timeout);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }
      const result: DetectionResult = await res.json();
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "done", result } : i));
    } catch (e: unknown) {
      clearTimeout(timeout);
      let msg = "Unknown error";
      if (e instanceof Error) {
        if (e.name === "AbortError") msg = "Timed out — try again";
        else if (e.message.includes("fetch") || e.message.includes("network")) msg = "Network error — check your connection";
        else msg = e.message;
      }
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "error", error: msg } : i));
    }
  }, []);

  const addUrl = useCallback((raw: string) => {
    const url = raw.trim();
    if (!url.startsWith("http")) return;
    const item: VideoItem = {
      id: Math.random().toString(36).slice(2),
      url,
      label: getPlatformLabel(url),
      status: "pending",
    };
    setItems(prev => [...prev, item]);
    analyzeItem(item);
    setUrlInput("");
  }, [analyzeItem]);

  const addFiles = useCallback((files: FileList | File[]) => {
    const valid = Array.from(files).filter(f => /\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name));
    const newItems: VideoItem[] = valid.map(f => ({
      id: Math.random().toString(36).slice(2),
      file: f,
      label: f.name,
      status: "pending",
    }));
    setItems(prev => [...prev, ...newItems]);
    const CONCURRENCY = 3;
    const chunks: VideoItem[][] = [];
    for (let i = 0; i < newItems.length; i += CONCURRENCY) chunks.push(newItems.slice(i, i + CONCURRENCY));
    (async () => { for (const chunk of chunks) await Promise.all(chunk.map(item => analyzeItem(item))); })();
  }, [analyzeItem]);

  const removeItem = (id: string) => setItems(prev => prev.filter(i => i.id !== id));
  const clearAll = () => setItems([]);

  const aiCount = items.filter(i => i.result?.is_ai_generated).length;
  const realCount = items.filter(i => i.result && !i.result.is_ai_generated).length;
  const analyzingCount = items.filter(i => i.status === "analyzing").length;
  const hasResults = items.length > 0;

  return (
    <div className="min-h-screen flex flex-col" style={{
      background: "radial-gradient(ellipse at 50% -10%, #1a0a3d 0%, #06060f 55%)"
    }}>

      {/* ── Navbar ── */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/6 backdrop-blur-sm sticky top-0 z-50 bg-[#06060f]/80">
        <div className="flex items-center gap-2.5">
          <Logo size={32} />
          <span className="font-bold text-lg tracking-tight">Verif<span className="text-violet-400">AI</span></span>
        </div>
        <div className="flex items-center gap-6 text-sm text-gray-500">
          <a href="#how" className="hover:text-white transition-colors hidden sm:block">How it works</a>
          <a href="#upload" className="hover:text-white transition-colors hidden sm:block">Detect</a>
          <a href="/train" className="px-4 py-1.5 rounded-full border border-violet-500/40 text-violet-300 hover:bg-violet-500/10 transition-colors text-sm">
            Train model
          </a>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="flex flex-col items-center text-center px-4 pt-20 pb-14">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/25 rounded-full px-4 py-1.5 text-xs text-violet-300 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
          File-level forensics · No frame decoding · Privacy safe
        </div>

        <div className="animate-float mb-6">
          <Logo size={72} />
        </div>

        <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight mb-4 leading-tight">
          <span className="text-white">Is this video</span>
          <br />
          <span className="shimmer-text">real or AI?</span>
        </h1>

        <p className="text-gray-400 text-lg max-w-lg mx-auto mb-8 leading-relaxed">
          VerifAI reads the hidden code inside every video file — frame timing, audio patterns,
          container signatures — to detect AI generation instantly.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          <Feature icon="🔍" text="Metadata forensics" />
          <Feature icon="🎵" text="Audio analysis" />
          <Feature icon="📊" text="Codec fingerprint" />
          <Feature icon="🤖" text="ML classifier" />
          <Feature icon="🔒" text="No upload stored" />
        </div>

        <a href="#upload"
          className="px-8 py-3.5 rounded-2xl font-semibold text-white text-sm transition-all duration-200 hover:scale-105"
          style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
          Detect a video →
        </a>
      </section>

      {/* ── How it works ── */}
      <section id="how" style={{ padding: "80px 16px", background: "rgba(255,255,255,0.015)" }}>
        <div className="max-w-3xl mx-auto">
          <div style={{ textAlign: "center", marginBottom: "48px" }}>
            <p style={{ fontSize: "11px", color: "#a78bfa", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: "12px" }}>How it works</p>
            <h2 style={{ fontSize: "36px", fontWeight: 800, color: "#ffffff" }}>Three layers of detection</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-10">
            <Step n="1" icon="🔬" title="Metadata scan"
              desc="Reads encoder tags, software signatures, and C2PA cryptographic markers embedded by AI tools." />
            <Step n="2" icon="📈" title="Codec analysis"
              desc="Measures frame timing uniformity, keyframe patterns, and audio silence — AI video has tell-tale statistical fingerprints." />
            <Step n="3" icon="🧠" title="ML classifier"
              desc="A trained model combines all signals to produce a final confidence score, improving with every labeled sample." />
          </div>
        </div>
      </section>

      {/* ── Stats bar ── */}
      <section style={{ borderTop: "1px solid rgba(255,255,255,0.07)", borderBottom: "1px solid rgba(255,255,255,0.07)", padding: "48px 16px", marginBottom: "56px", background: "rgba(255,255,255,0.02)" }}>
        <div className="max-w-3xl mx-auto grid grid-cols-3 gap-4" style={{ textAlign: "center" }}>
          <div>
            <p style={{ fontSize: "40px", fontWeight: 800, color: "#ffffff" }}>20+</p>
            <p style={{ fontSize: "13px", color: "#9ca3af", marginTop: "6px" }}>AI tools detected</p>
          </div>
          <div>
            <p style={{ fontSize: "40px", fontWeight: 800, color: "#ffffff" }}>0</p>
            <p style={{ fontSize: "13px", color: "#9ca3af", marginTop: "6px" }}>frames decoded</p>
          </div>
          <div>
            <p style={{ fontSize: "40px", fontWeight: 800, color: "#ffffff" }}>~3s</p>
            <p style={{ fontSize: "13px", color: "#9ca3af", marginTop: "6px" }}>avg detection time</p>
          </div>
        </div>
      </section>

      {/* ── Upload / Detect ── */}
      <section id="upload" className="flex-1 px-4 pb-20">
        <div className="max-w-2xl mx-auto space-y-5">
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-white mb-2">Detect a video</h2>
            <p className="text-gray-500 text-sm">Drop one or multiple files — results appear as each is analyzed</p>
          </div>

          {/* URL input */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-gray-500 text-sm">
                🔗
              </div>
              <input
                type="url"
                value={urlInput}
                onChange={e => setUrlInput(e.target.value)}
                onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && addUrl(urlInput)}
                placeholder="Paste TikTok, Reels, YouTube, Twitter… link"
                className="w-full pl-10 pr-4 py-3.5 rounded-2xl bg-white/5 border border-white/10 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-violet-500/60 focus:bg-white/7 transition-all"
              />
            </div>
            <button
              onClick={() => addUrl(urlInput)}
              disabled={!urlInput.startsWith("http")}
              className="px-5 py-3.5 rounded-2xl text-sm font-semibold text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:scale-105"
              style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}
            >
              Detect
            </button>
          </div>

          <div className="flex items-center gap-3 text-xs text-gray-700">
            <div className="flex-1 h-px bg-white/8" />
            <span>or upload a file</span>
            <div className="flex-1 h-px bg-white/8" />
          </div>

          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => { e.preventDefault(); setIsDragging(false); addFiles(e.dataTransfer.files); }}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            className={`w-full h-52 rounded-3xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-4 transition-all duration-200 ${
              isDragging
                ? "border-violet-400 bg-violet-500/10 scale-[1.01]"
                : "border-white/12 bg-white/2 hover:border-violet-400/50 hover:bg-white/4"
            }`}
          >
            <div className="w-16 h-16 rounded-3xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)" }}>
              <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.9L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-white font-semibold">Drop videos here</p>
              <p className="text-gray-500 text-sm mt-0.5">or click to browse · multiple files OK</p>
              <p className="text-gray-600 text-xs mt-1">MP4 · MOV · MKV · WebM · M4V</p>
            </div>
            <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v" multiple className="hidden"
              onChange={e => e.target.files && addFiles(e.target.files)} />
          </div>

          {/* Summary */}
          {hasResults && (
            <div className="flex items-center justify-between text-sm">
              <div className="flex gap-4">
                {analyzingCount > 0 && <span className="text-violet-400 font-medium">⏳ {analyzingCount} analyzing</span>}
                {aiCount > 0 && <span className="text-red-400 font-medium">⚠ {aiCount} AI</span>}
                {realCount > 0 && <span className="text-green-400 font-medium">✓ {realCount} Real</span>}
              </div>
              <button onClick={clearAll} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                Clear all
              </button>
            </div>
          )}

          {/* Results */}
          <div className="space-y-3">
            {items.map(item => (
              <ResultCard key={item.id} item={item}
                onRemove={() => removeItem(item.id)}
                onRetry={() => analyzeItem({ ...item })} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/6 py-8 px-4">
        <div className="max-w-3xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-gray-600">
          <div className="flex items-center gap-2">
            <Logo size={20} />
            <span className="font-semibold text-gray-500">VerifAI</span>
            <span>· No videos stored · No frames decoded</span>
          </div>
          <div className="flex gap-4">
            <a href="/train" className="hover:text-gray-400 transition-colors">Train model</a>
            <span>·</span>
            <span>Built with file-level forensics</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
