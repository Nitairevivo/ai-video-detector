"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";

const HISTORY_KEY = "aivd_history";
const MAX_HISTORY = 50;

const API = process.env.NEXT_PUBLIC_API_URL || "https://ai-video-detector-production-a305.up.railway.app";

type DetectionResult = {
  filename?: string;
  url?: string;
  is_ai_generated: boolean;
  verdict: "ai_generated" | "ai_edited" | "real";
  confidence: number;
  ai_tool_detected: string | null;
  edit_tool_detected: string | null;
  detection_method: string;
  signals?: Record<string, number>;
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

function getVerdictStyle(r: DetectionResult) {
  const v = r.verdict ?? (r.is_ai_generated ? "ai_generated" : "real");
  if (v === "ai_generated") return {
    color: "#ef4444", bg: "rgba(239,68,68,0.06)", border: "rgba(239,68,68,0.25)",
    badge: "bg-red-500/20 text-red-300", dot: "bg-red-400",
    label: "🤖 AI GENERATED",
    title: r.ai_tool_detected ? `Made with ${r.ai_tool_detected}` : "AI-Generated Video",
  };
  if (v === "ai_edited") return {
    color: "#a855f7", bg: "rgba(168,85,247,0.06)", border: "rgba(168,85,247,0.25)",
    badge: "bg-purple-500/20 text-purple-300", dot: "bg-purple-400",
    label: "✏️ AI EDITED",
    title: r.edit_tool_detected ? `Edited with ${r.edit_tool_detected}` : "Real Video, AI-Edited",
  };
  return {
    color: "#22c55e", bg: "rgba(34,197,94,0.06)", border: "rgba(34,197,94,0.25)",
    badge: "bg-green-500/20 text-green-300", dot: "bg-green-400",
    label: "✅ AUTHENTIC",
    title: "Real Footage",
  };
}

// ── Logo ─────────────────────────────────────────────────────────────────────
function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
      <rect width="36" height="36" rx="10" fill="url(#lg)" />
      <path d="M7 18C7 18 11.5 11 18 11C24.5 11 29 18 29 18C29 18 24.5 25 18 25C11.5 25 7 18 7 18Z"
        stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="18" cy="18" r="3.5" fill="white" />
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

// ── Confidence ring ───────────────────────────────────────────────────────────
function ConfidenceMeter({ value, color }: { value: number; color: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="relative w-24 h-24 flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#1a1a2e" strokeWidth="8" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
          strokeLinecap="round" strokeDasharray={`${2.51 * pct} 251`}
          style={{ transition: "stroke-dasharray 1s ease" }} />
      </svg>
      <div className="text-center z-10">
        <div className="text-xl font-bold" style={{ color }}>{pct}%</div>
        <div className="text-[9px] text-gray-500 mt-0.5">confidence</div>
      </div>
    </div>
  );
}

// ── Result card ───────────────────────────────────────────────────────────────
function ResultCard({ item, onRemove, onRetry }: { item: VideoItem; onRemove: () => void; onRetry?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const r = item.result;

  if (item.status === "analyzing") {
    return (
      <div className="bg-white/3 border border-white/8 rounded-2xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-violet-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium truncate">{item.label}</p>
          <p className="text-gray-500 text-xs mt-0.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse inline-block" />
            {item.file ? `Analyzing · ${(item.file.size/1024/1024).toFixed(1)} MB` : "Analyzing video…"}
          </p>
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
  const style = getVerdictStyle(r);

  return (
    <div className="rounded-2xl overflow-hidden transition-all duration-300" style={{ background: style.bg, border: `1px solid ${style.border}` }}>
      <div style={{ height: 3, background: style.color }} />
      <div className="p-5 flex items-center gap-4">
        <ConfidenceMeter value={r.confidence} color={style.color} />
        <div className="flex-1 min-w-0">
          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold mb-2 ${style.badge}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
            {style.label}
          </div>
          <p className="text-white font-semibold text-sm">{style.title}</p>
          <p className="text-gray-500 text-xs mt-0.5 truncate">{item.label}</p>
          <p className="text-gray-600 text-xs mt-1 truncate">{r.detection_method}</p>
          <div className="flex items-center gap-3 mt-2">
            {r.signals && (
              <button onClick={() => setExpanded(v => !v)} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                {expanded ? "Hide details ↑" : "Show details ↓"}
              </button>
            )}
            {item.url && (
              <button onClick={() => {
                const pct = Math.round(r.confidence * 100);
                const verdict = r.verdict === "ai_generated" ? "🤖 AI Generated" : r.verdict === "ai_edited" ? "✏️ AI Edited" : "✅ Real";
                navigator.clipboard.writeText(`${verdict} (${pct}%) — ${item.url}\nDetected by VerifAI`);
              }} className="text-xs text-gray-600 hover:text-violet-400 transition-colors">
                Copy result
              </button>
            )}
          </div>
        </div>
        <button onClick={onRemove} className="text-gray-700 hover:text-gray-400 text-sm px-1 flex-shrink-0">✕</button>
      </div>

      {expanded && r.signals && (
        <div className="px-5 pb-5 border-t border-white/5 pt-4 space-y-1.5">
          {Object.entries(r.signals).filter(([,v]) => typeof v === "number").slice(0, 12).map(([key, val]) => (
            <div key={key} className="flex justify-between items-center text-xs">
              <span className="text-gray-500">{key.replace(/_/g, " ")}</span>
              <span className="font-mono font-semibold text-gray-400">
                {val === 1 ? "✓ YES" : val === 0 ? "— NO" : (val as number).toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Step ──────────────────────────────────────────────────────────────────────
function Step({ n, title, desc, icon }: { n: string; title: string; desc: string; icon: string }) {
  return (
    <div className="flex flex-col items-center text-center gap-3">
      <div className="w-14 h-14 rounded-2xl bg-white/6 border border-white/10 flex items-center justify-center text-3xl">{icon}</div>
      <div className="w-6 h-6 rounded-full bg-violet-500/30 border border-violet-400/50 flex items-center justify-center text-[11px] text-violet-300 font-bold">{n}</div>
      <div>
        <p className="text-white font-semibold text-sm mb-1">{title}</p>
        <p className="text-gray-400 text-xs leading-relaxed">{desc}</p>
      </div>
    </div>
  );
}

// ── Platform icons ────────────────────────────────────────────────────────────
const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "🐦", x: "🐦",
  reddit: "🤖", facebook: "👤", telegram: "✈️",
};
function getPlatformLabel(url: string) {
  try {
    const host = new URL(url).hostname.replace("www.", "");
    return `${PLATFORM_ICONS[host.split(".")[0]] ?? "🔗"} ${host}`;
  } catch { return url.slice(0, 60); }
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const [items, setItems] = useState<VideoItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [deepMode, setDeepMode] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<Array<{url: string; label: string; verdict: string; confidence: number; tool: string | null; date: string}>>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  // Load history from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(HISTORY_KEY);
      if (saved) setHistory(JSON.parse(saved));
    } catch {}
  }, []);

  const analyzeItem = useCallback(async (item: VideoItem, deep = false) => {
    setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "analyzing" } : i));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), deep ? 180_000 : 120_000);
    try {
      let res: Response;
      if (item.url) {
        res = await fetch(`${API}/detect-url?deep=${deep}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: item.url }),
          signal: controller.signal,
        });
      } else {
        const form = new FormData();
        form.append("file", item.file!);
        res = await fetch(`${API}/detect?deep=${deep}`, { method: "POST", body: form, signal: controller.signal });
      }
      clearTimeout(timeout);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || `Server error ${res.status}`);
      }
      const result: DetectionResult = await res.json();
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "done", result } : i));
      // Save to history
      if (item.url) {
        const entry = { url: item.url, label: item.label, verdict: result.verdict, confidence: result.confidence, tool: result.ai_tool_detected, date: new Date().toISOString() };
        setHistory(prev => {
          const updated = [entry, ...prev.filter(h => h.url !== item.url)].slice(0, MAX_HISTORY);
          try { localStorage.setItem(HISTORY_KEY, JSON.stringify(updated)); } catch {}
          return updated;
        });
      }
    } catch (e: unknown) {
      clearTimeout(timeout);
      let msg = "Unknown error";
      if (e instanceof Error) {
        if (e.name === "AbortError") msg = "Timed out — video may be too large";
        else msg = e.message;
      }
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "error", error: msg } : i));
    }
  }, []);

  const addUrls = useCallback((raw: string) => {
    const urls = raw.split(/[\n,\s]+/).map(s => s.trim()).filter(s => s.startsWith("http"));
    if (!urls.length) return;
    const newItems: VideoItem[] = urls.map(url => ({
      id: Math.random().toString(36).slice(2), url,
      label: getPlatformLabel(url), status: "pending" as const,
    }));
    setItems(prev => [...newItems, ...prev]);
    newItems.forEach(item => analyzeItem(item, deepMode));
    setUrlInput("");
  }, [analyzeItem, deepMode]);

  const addFiles = useCallback((files: FileList | File[]) => {
    const valid = Array.from(files).filter(f => /\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name));
    const newItems: VideoItem[] = valid.map(f => ({ id: Math.random().toString(36).slice(2), file: f, label: f.name, status: "pending" as const }));
    setItems(prev => [...newItems, ...prev]);
    newItems.forEach(item => analyzeItem(item, deepMode));
  }, [analyzeItem]);

  const aiCount = items.filter(i => i.result?.verdict === "ai_generated").length;
  const editedCount = items.filter(i => i.result?.verdict === "ai_edited").length;
  const realCount = items.filter(i => i.result?.verdict === "real").length;
  const analyzingCount = items.filter(i => i.status === "analyzing").length;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "radial-gradient(ellipse at 50% -10%, #1a0a3d 0%, #06060f 55%)" }}>

      {/* Navbar */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/6 backdrop-blur-sm sticky top-0 z-50 bg-[#06060f]/80">
        <div className="flex items-center gap-2.5">
          <Logo size={32} />
          <span className="font-bold text-lg tracking-tight">Verif<span className="text-violet-400">AI</span></span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <a href="#how" className="text-gray-500 hover:text-white transition-colors hidden sm:block">How it works</a>
          <a href="#upload" className="px-4 py-1.5 rounded-full border border-violet-500/40 text-violet-300 hover:bg-violet-500/10 transition-colors text-sm">
            Detect video
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex flex-col items-center text-center px-4 pt-20 pb-14">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/25 rounded-full px-4 py-1.5 text-xs text-violet-300 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
          Powered by Gemini Vision AI · Metadata forensics · Privacy safe
        </div>

        <div className="mb-6"><Logo size={72} /></div>

        <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight mb-4 leading-tight">
          <span className="text-white">Is this video</span><br />
          <span className="shimmer-text">real or AI?</span>
        </h1>

        <p className="text-gray-400 text-lg max-w-lg mx-auto mb-8 leading-relaxed">
          VerifAI detects AI-generated videos using metadata forensics and Gemini Vision AI —
          even when TikTok and Instagram strip all metadata.
        </p>

        {/* Three verdict pills */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/25 rounded-full px-4 py-2 text-sm text-red-300">
            🤖 AI Generated
          </div>
          <div className="flex items-center gap-2 bg-purple-500/10 border border-purple-500/25 rounded-full px-4 py-2 text-sm text-purple-300">
            ✏️ AI Edited
          </div>
          <div className="flex items-center gap-2 bg-green-500/10 border border-green-500/25 rounded-full px-4 py-2 text-sm text-green-300">
            ✅ Authentic
          </div>
        </div>

        <a href="#upload"
          className="px-8 py-3.5 rounded-2xl font-semibold text-white text-sm transition-all duration-200 hover:scale-105"
          style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
          Detect a video →
        </a>
      </section>

      {/* How it works */}
      <section id="how" className="py-20 px-4" style={{ background: "rgba(255,255,255,0.015)" }}>
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-xs text-violet-400 font-bold tracking-widest uppercase mb-3">How it works</p>
            <h2 className="text-4xl font-extrabold text-white">Three layers of detection</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-10">
            <Step n="1" icon="🔬" title="Metadata scan"
              desc="Reads AI tool signatures, C2PA markers, and encoder tags embedded by Sora, Kling, Runway and others." />
            <Step n="2" icon="👁️" title="Gemini Vision"
              desc="When metadata is absent (TikTok strips it), Gemini Vision AI analyzes 6 video frames for AI artifacts." />
            <Step n="3" icon="🧠" title="3 verdicts"
              desc="AI Generated (created by AI), AI Edited (real footage with AI effects), or Authentic (real camera footage)." />
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-12 px-4 border-y border-white/7" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="max-w-3xl mx-auto grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-4xl font-extrabold text-white">30+</p>
            <p className="text-xs text-gray-500 mt-1.5">AI tools detected</p>
          </div>
          <div>
            <p className="text-4xl font-extrabold text-white">3</p>
            <p className="text-xs text-gray-500 mt-1.5">verdict categories</p>
          </div>
          <div>
            <p className="text-4xl font-extrabold text-white">~5s</p>
            <p className="text-xs text-gray-500 mt-1.5">avg detection time</p>
          </div>
        </div>
      </section>

      {/* Upload / Detect */}
      <section id="upload" className="flex-1 px-4 py-16">
        <div className="max-w-2xl mx-auto space-y-5">
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-white mb-2">Detect a video</h2>
            <p className="text-gray-500 text-sm">Paste a TikTok/Instagram/YouTube link or upload a file</p>
          </div>

          {/* Deep mode toggle */}
          <div className="flex items-center justify-between px-4 py-3 rounded-2xl bg-white/3 border border-white/8">
            <div>
              <p className="text-sm font-semibold text-white">Deep Analysis</p>
              <p className="text-xs text-gray-600 mt-0.5">Visual + frequency scan — detects re-encoded AI videos (~10s extra)</p>
            </div>
            <button
              onClick={() => setDeepMode(d => !d)}
              className={`relative w-11 h-6 rounded-full transition-all duration-200 flex-shrink-0 ${deepMode ? "bg-violet-600" : "bg-white/10"}`}>
              <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all duration-200 ${deepMode ? "left-5" : "left-0.5"}`} />
            </button>
          </div>

          {/* URL input — supports single or multiple URLs */}
          <div className="space-y-2">
            <textarea
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); addUrls(urlInput); }
              }}
              placeholder={"Paste one or multiple links (TikTok, Instagram, YouTube…)\nOne per line for batch analysis"}
              rows={urlInput.split("\n").length > 1 ? Math.min(urlInput.split("\n").length + 1, 5) : 1}
              className="w-full px-4 py-3.5 rounded-2xl bg-white/5 border border-white/10 text-white text-sm placeholder-gray-600 focus:outline-none focus:border-violet-500/60 transition-all resize-none leading-relaxed"
            />
            <div className="flex gap-2">
              <button onClick={() => addUrls(urlInput)}
                disabled={!urlInput.split(/[\n,\s]+/).some(s => s.trim().startsWith("http"))}
                className="flex-1 py-3 rounded-2xl text-sm font-semibold text-white transition-all disabled:opacity-30 hover:scale-[1.02]"
                style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
                {urlInput.split(/[\n,\s]+/).filter(s => s.trim().startsWith("http")).length > 1
                  ? `Detect ${urlInput.split(/[\n,\s]+/).filter(s => s.trim().startsWith("http")).length} videos`
                  : "Detect"}
              </button>
              {history.length > 0 && (
                <button onClick={() => setShowHistory(v => !v)}
                  className="px-4 py-3 rounded-2xl text-sm font-medium border border-white/10 text-gray-400 hover:text-white hover:border-white/20 transition-all">
                  {showHistory ? "Hide" : `History (${history.length})`}
                </button>
              )}
            </div>
          </div>

          {/* History panel */}
          {showHistory && history.length > 0 && (
            <div className="rounded-2xl bg-white/3 border border-white/8 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/6">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Recent checks</span>
                <button onClick={() => { setHistory([]); localStorage.removeItem(HISTORY_KEY); }} className="text-xs text-gray-600 hover:text-red-400 transition-colors">Clear</button>
              </div>
              <div className="divide-y divide-white/5 max-h-64 overflow-y-auto">
                {history.map((h, i) => {
                  const color = h.verdict === "ai_generated" ? "#ef4444" : h.verdict === "ai_edited" ? "#a855f7" : "#22c55e";
                  const icon = h.verdict === "ai_generated" ? "🤖" : h.verdict === "ai_edited" ? "✏️" : "✅";
                  return (
                    <button key={i} onClick={() => { setUrlInput(h.url); setShowHistory(false); }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/4 transition-colors text-left">
                      <span className="text-base flex-shrink-0">{icon}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-white truncate">{h.label}</p>
                        <p className="text-[10px] text-gray-600 truncate">{h.url}</p>
                      </div>
                      <span className="text-xs font-bold flex-shrink-0" style={{ color }}>{Math.round(h.confidence * 100)}%</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 text-xs text-gray-700">
            <div className="flex-1 h-px bg-white/8" /><span>or upload a file</span><div className="flex-1 h-px bg-white/8" />
          </div>

          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => { e.preventDefault(); setIsDragging(false); addFiles(e.dataTransfer.files); }}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            className={`w-full h-48 rounded-3xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-3 transition-all duration-200 ${
              isDragging ? "border-violet-400 bg-violet-500/10 scale-[1.01]" : "border-white/12 bg-white/2 hover:border-violet-400/50 hover:bg-white/4"
            }`}>
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl"
              style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>🎬</div>
            <div className="text-center">
              <p className="text-white font-semibold text-sm">Drop video here</p>
              <p className="text-gray-500 text-xs mt-0.5">MP4 · MOV · MKV · WebM · M4V</p>
            </div>
            <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v" multiple className="hidden"
              onChange={e => e.target.files && addFiles(e.target.files)} />
          </div>

          {/* Summary bar */}
          {items.length > 0 && (
            <div className="flex items-center justify-between text-sm">
              <div className="flex gap-4">
                {analyzingCount > 0 && <span className="text-violet-400 font-medium">⏳ {analyzingCount} analyzing</span>}
                {aiCount > 0 && <span className="text-red-400 font-medium">🤖 {aiCount} AI</span>}
                {editedCount > 0 && <span className="text-purple-400 font-medium">✏️ {editedCount} Edited</span>}
                {realCount > 0 && <span className="text-green-400 font-medium">✅ {realCount} Real</span>}
              </div>
              <button onClick={() => setItems([])} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                Clear all
              </button>
            </div>
          )}

          {/* Results */}
          <div className="space-y-3">
            {items.map(item => (
              <ResultCard key={item.id} item={item}
                onRemove={() => setItems(prev => prev.filter(i => i.id !== item.id))}
                onRetry={() => analyzeItem({ ...item })} />
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/6 py-8 px-4">
        <div className="max-w-3xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-gray-600">
          <div className="flex items-center gap-2">
            <Logo size={20} />
            <span className="font-semibold text-gray-500">VerifAI</span>
            <span>· No videos stored · Privacy safe</span>
          </div>
          <span>Powered by Gemini Vision AI</span>
        </div>
      </footer>
    </div>
  );
}
