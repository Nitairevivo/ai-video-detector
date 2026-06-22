"use client";

import { useState, useRef, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  file: File;
  status: "pending" | "analyzing" | "done" | "error";
  result?: DetectionResult;
  error?: string;
  retries?: number;
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
};

function ConfidenceMeter({ value, isAI }: { value: number; isAI: boolean }) {
  const pct = Math.round(value * 100);
  const color = isAI ? "#f97316" : "#4ade80";
  return (
    <div className="relative w-36 h-36 flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="42" fill="none" stroke="#1a1a2e" strokeWidth="8" />
        <circle cx="50" cy="50" r="42" fill="none" stroke={color} strokeWidth="8"
          strokeLinecap="round" strokeDasharray={`${2.64 * pct} 264`}
          style={{ transition: "stroke-dasharray 1s ease" }} />
      </svg>
      <div className="text-center z-10">
        <div className="text-3xl font-bold" style={{ color }}>{pct}%</div>
        <div className="text-xs text-gray-400 mt-0.5">confidence</div>
      </div>
    </div>
  );
}

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
        <div>
          <p className="text-white text-sm font-medium truncate max-w-xs">{item.file.name}</p>
          <p className="text-gray-500 text-xs mt-0.5">Reading file signatures… · {(item.file.size / 1024 / 1024).toFixed(1)} MB</p>
        </div>
      </div>
    );
  }

  if (item.status === "error") {
    return (
      <div className="bg-red-500/5 border border-red-500/20 rounded-2xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center flex-shrink-0 text-lg">❌</div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium truncate">{item.file.name}</p>
          <p className="text-red-400 text-xs mt-0.5">{item.error}</p>
          {onRetry && (
            <button onClick={onRetry}
              className="text-xs text-violet-400 hover:text-violet-300 mt-1.5 transition-colors underline underline-offset-2">
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
  const color = isAI ? "red" : "green";

  return (
    <div className={`border rounded-2xl overflow-hidden ${isAI ? "bg-red-500/5 border-red-500/20" : "bg-green-500/5 border-green-500/20"}`}>
      {/* Main row */}
      <div className="p-5 flex items-center gap-4">
        <ConfidenceMeter value={r.confidence} isAI={isAI} />
        <div className="flex-1 min-w-0">
          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold mb-2 ${isAI ? "bg-red-500/20 text-red-300" : "bg-green-500/20 text-green-300"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isAI ? "bg-red-400" : "bg-green-400"}`} />
            {isAI ? "AI GENERATED" : "AUTHENTIC"}
          </div>
          <p className="text-white font-semibold text-sm truncate">
            {isAI ? (r.ai_tool_detected ? `Made with ${r.ai_tool_detected}` : "AI-Generated") : "Real Footage"}
          </p>
          <p className="text-gray-500 text-xs mt-0.5 truncate">{item.file.name}</p>
          <button onClick={() => setExpanded(v => !v)}
            className="text-xs text-gray-600 hover:text-gray-400 mt-2 transition-colors">
            {expanded ? "Hide details ↑" : "Show details ↓"}
          </button>
        </div>
        <button onClick={onRemove} className="text-gray-700 hover:text-gray-400 text-sm px-1 flex-shrink-0">✕</button>
      </div>

      {/* Expanded signals */}
      {expanded && (
        <div className="px-5 pb-5 border-t border-white/5 pt-4 space-y-1.5">
          {Object.entries(SIGNAL_LABELS).map(([key, label]) =>
            r.signals[key] !== undefined ? (
              <div key={key} className="flex justify-between items-center text-xs">
                <span className="text-gray-500">{label}</span>
                <span className={`font-mono font-semibold ${
                  (r.signals[key] === 1 || (r.signals[key] > 0.6 && r.signals[key] !== 1 && r.signals[key] !== 0))
                    ? "text-orange-400" : "text-gray-400"
                }`}>
                  {r.signals[key] === 0 || r.signals[key] === 1
                    ? (r.signals[key] === 1 ? "✓ YES" : "— NO")
                    : r.signals[key].toFixed(4)}
                </span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [items, setItems] = useState<VideoItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const analyzeFile = useCallback(async (item: VideoItem) => {
    setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "analyzing" } : i));
    const form = new FormData();
    form.append("file", item.file);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000); // 60s timeout
    try {
      const res = await fetch(`${API}/detect`, { method: "POST", body: form, signal: controller.signal });
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
        if (e.name === "AbortError") msg = "Timed out after 60s — try a smaller file";
        else if (e.message.includes("fetch") || e.message.toLowerCase().includes("load") || e.message.includes("network"))
          msg = "Network error — check your connection and try again";
        else msg = e.message;
      }
      setItems(prev => prev.map(i => i.id === item.id
        ? { ...i, status: "error", error: msg, retries: (i.retries ?? 0) }
        : i));
    }
  }, []);

  const addFiles = useCallback((files: FileList | File[]) => {
    const valid = Array.from(files).filter(f =>
      /\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name)
    );
    const newItems: VideoItem[] = valid.map(f => ({
      id: Math.random().toString(36).slice(2),
      file: f,
      status: "pending",
    }));
    setItems(prev => [...prev, ...newItems]);
    // Analyze up to 3 in parallel to avoid overwhelming the server
    const CONCURRENCY = 3;
    const chunks: VideoItem[][] = [];
    for (let i = 0; i < newItems.length; i += CONCURRENCY)
      chunks.push(newItems.slice(i, i + CONCURRENCY));
    (async () => {
      for (const chunk of chunks)
        await Promise.all(chunk.map(item => analyzeFile(item)));
    })();
  }, [analyzeFile]);

  const removeItem = (id: string) => setItems(prev => prev.filter(i => i.id !== id));
  const retryItem = useCallback((item: VideoItem) => {
    analyzeFile({ ...item, retries: (item.retries ?? 0) + 1 });
  }, [analyzeFile]);
  const clearAll = () => setItems([]);

  const doneCount = items.filter(i => i.status === "done").length;
  const aiCount = items.filter(i => i.result?.is_ai_generated).length;
  const realCount = items.filter(i => i.result && !i.result.is_ai_generated).length;
  const analyzingCount = items.filter(i => i.status === "analyzing").length;

  return (
    <main className="min-h-screen px-4 py-14"
      style={{ background: "radial-gradient(ellipse at 50% 0%, #0d0d2b 0%, #07070f 60%)" }}>
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 text-xs text-gray-400 mb-5">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            File-level forensics · No frame decoding
          </div>
          <h1 className="text-5xl font-bold tracking-tight mb-3">
            <span className="text-white">AI Video</span>{" "}
            <span style={{ background: "linear-gradient(135deg, #6366f1, #a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Detector
            </span>
          </h1>
          <p className="text-gray-400 text-base max-w-md mx-auto">
            Upload one or multiple videos — results appear as each file is analyzed.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onClick={() => fileRef.current?.click()}
          onDrop={(e) => { e.preventDefault(); setIsDragging(false); addFiles(e.dataTransfer.files); }}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          className={`w-full h-48 rounded-2xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-3 transition-all duration-300 ${
            isDragging ? "border-violet-400 bg-violet-500/10 scale-[1.01]" : "border-white/15 bg-white/3 hover:border-white/25 hover:bg-white/5"
          }`}
        >
          <div className="w-14 h-14 rounded-2xl bg-violet-500/15 flex items-center justify-center">
            <svg className="w-7 h-7 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.9L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-white font-medium">Drop videos here</p>
            <p className="text-gray-500 text-sm mt-0.5">or click to browse · multiple files supported</p>
            <p className="text-gray-600 text-xs mt-1">MP4 · MOV · MKV · WebM</p>
          </div>
          <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v"
            multiple className="hidden"
            onChange={e => e.target.files && addFiles(e.target.files)} />
        </div>

        {/* Summary bar */}
        {items.length > 0 && (
          <div className="flex items-center justify-between">
            <div className="flex gap-4 text-sm">
              {analyzingCount > 0 && (
                <span className="text-violet-400 font-medium">⏳ {analyzingCount} analyzing...</span>
              )}
              {aiCount > 0 && (
                <span className="text-red-400 font-medium">⚠️ {aiCount} AI</span>
              )}
              {realCount > 0 && (
                <span className="text-green-400 font-medium">✅ {realCount} Real</span>
              )}
            </div>
            <button onClick={clearAll}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Clear all
            </button>
          </div>
        )}

        {/* Results list */}
        <div className="space-y-3">
          {items.map(item => (
            <ResultCard key={item.id} item={item} onRemove={() => removeItem(item.id)} onRetry={() => retryItem(item)} />
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-center gap-4 text-xs text-gray-700 pt-4">
          <a href="/train" className="hover:text-gray-400 transition-colors underline underline-offset-2">
            🧠 Train model
          </a>
          <span>·</span>
          <span>No frames decoded or stored</span>
        </div>

      </div>
    </main>
  );
}
