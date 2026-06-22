"use client";

import { useState, useRef, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Signal = { [key: string]: number };

type DetectionResult = {
  filename: string;
  is_ai_generated: boolean;
  confidence: number;
  confidence_pct: string;
  ai_tool_detected: string | null;
  detection_method: string;
  signals: Signal;
  rule_based_confidence: number;
  ml_confidence: number | null;
};

type Status = "idle" | "analyzing" | "done" | "error";

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
    <div className="relative w-44 h-44 flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="42" fill="none" stroke="#1a1a2e" strokeWidth="8" />
        <circle
          cx="50" cy="50" r="42" fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${2.64 * pct} 264`}
          style={{ transition: "stroke-dasharray 1s ease" }}
        />
      </svg>
      <div className="text-center z-10">
        <div className="text-4xl font-bold" style={{ color }}>{pct}%</div>
        <div className="text-xs text-gray-400 mt-1">confidence</div>
      </div>
    </div>
  );
}

function SignalRow({ label, value }: { label: string; value: number }) {
  const isBool = value === 0 || value === 1;
  const display = isBool ? (value === 1 ? "✓ YES" : "— NO") : value.toFixed(4);
  const highlight = isBool ? value === 1 : value > 0.6;
  return (
    <div className="flex justify-between items-center py-2 border-b border-white/5">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-mono font-semibold ${highlight ? "text-orange-400" : "text-gray-300"}`}>
        {display}
      </span>
    </div>
  );
}

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [error, setError] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const analyze = useCallback(async (file: File) => {
    setStatus("analyzing");
    setResult(null);
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/detect`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Detection failed");
      }
      setResult(await res.json());
      setStatus("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setStatus("error");
    }
  }, []);

  const onFile = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["mp4", "mov", "mkv", "webm", "m4v"].includes(ext)) {
      setError("Unsupported format. Use MP4, MOV, MKV or WebM.");
      setStatus("error");
      return;
    }
    analyze(file);
  };

  const reset = () => { setStatus("idle"); setResult(null); setError(""); };

  return (
    <main
      className="min-h-screen flex flex-col items-center px-4 py-16"
      style={{ background: "radial-gradient(ellipse at 50% 0%, #0d0d2b 0%, #07070f 60%)" }}
    >
      {/* Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 text-xs text-gray-400 mb-6">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          File-level forensics · No frame decoding
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-3">
          <span className="text-white">AI Video</span>{" "}
          <span style={{ background: "linear-gradient(135deg, #6366f1, #a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Detector
          </span>
        </h1>
        <p className="text-gray-400 text-lg max-w-md mx-auto">
          Reads binary signatures inside the video file to detect AI generation — in milliseconds.
        </p>
      </div>

      {/* Upload zone */}
      {status === "idle" && (
        <div
          onClick={() => fileRef.current?.click()}
          onDrop={(e) => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          className={`w-full max-w-xl h-64 rounded-2xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-4 transition-all duration-300 ${
            isDragging ? "border-violet-400 bg-violet-500/10 scale-[1.02]" : "border-white/15 bg-white/3 hover:border-white/30 hover:bg-white/5"
          }`}
        >
          <div className="w-16 h-16 rounded-2xl bg-violet-500/15 flex items-center justify-center">
            <svg className="w-8 h-8 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.9L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-white font-medium">Drop a video file here</p>
            <p className="text-gray-500 text-sm mt-1">or click to browse · MP4, MOV, MKV, WebM</p>
          </div>
          <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v" className="hidden"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        </div>
      )}

      {/* Analyzing spinner */}
      {status === "analyzing" && (
        <div className="flex flex-col items-center gap-6">
          <div className="relative w-28 h-28">
            <div className="absolute inset-0 rounded-full border-2 border-violet-400/20 animate-ping" />
            <div className="w-28 h-28 rounded-full bg-violet-500/10 border border-violet-400/30 flex items-center justify-center">
              <svg className="w-10 h-10 text-violet-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
          </div>
          <div className="text-center">
            <p className="text-white font-semibold">Reading file signatures...</p>
            <p className="text-gray-500 text-sm mt-1">Scanning metadata · codec · container structure</p>
          </div>
        </div>
      )}

      {/* Error */}
      {status === "error" && (
        <div className="w-full max-w-xl text-center">
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-8 mb-6">
            <p className="text-red-400 text-lg font-semibold mb-2">Detection Failed</p>
            <p className="text-gray-400 text-sm">{error}</p>
          </div>
          <button onClick={reset} className="px-6 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-medium transition-colors">
            Try Again
          </button>
        </div>
      )}

      {/* Result */}
      {status === "done" && result && (
        <div className="w-full max-w-2xl space-y-4">
          {/* Verdict card */}
          <div className={`rounded-2xl p-8 border flex flex-col sm:flex-row items-center gap-8 ${
            result.is_ai_generated ? "bg-red-500/5 border-red-500/25" : "bg-green-500/5 border-green-500/25"
          }`}>
            <ConfidenceMeter value={result.confidence} isAI={result.is_ai_generated} />
            <div className="flex-1 text-center sm:text-left">
              <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold mb-3 ${
                result.is_ai_generated ? "bg-red-500/20 text-red-300" : "bg-green-500/20 text-green-300"
              }`}>
                <span className={`w-2 h-2 rounded-full ${result.is_ai_generated ? "bg-red-400" : "bg-green-400"}`} />
                {result.is_ai_generated ? "AI GENERATED" : "AUTHENTIC"}
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">
                {result.is_ai_generated
                  ? (result.ai_tool_detected ? `Made with ${result.ai_tool_detected}` : "AI-Generated Video")
                  : "Real / Camera Footage"}
              </h2>
              <p className="text-gray-400 text-sm">{result.detection_method}</p>
              {result.ai_tool_detected && (
                <div className="mt-3 inline-flex items-center gap-2 bg-orange-500/10 border border-orange-500/20 rounded-lg px-3 py-1.5">
                  <span className="text-xs text-orange-300 font-medium">Tool: {result.ai_tool_detected}</span>
                </div>
              )}
            </div>
          </div>

          {/* Signals */}
          <div className="bg-white/3 border border-white/8 rounded-2xl p-6">
            <h3 className="text-xs font-semibold text-gray-500 mb-4 uppercase tracking-wider">Detection Signals</h3>
            {Object.entries(SIGNAL_LABELS).map(([key, label]) =>
              result.signals[key] !== undefined ? (
                <SignalRow key={key} label={label} value={result.signals[key]} />
              ) : null
            )}
          </div>

          {/* Score grid */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white/3 border border-white/8 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-violet-400">{Math.round(result.rule_based_confidence * 100)}%</div>
              <div className="text-xs text-gray-500 mt-1">Rule-based score</div>
            </div>
            <div className="bg-white/3 border border-white/8 rounded-xl p-4 text-center">
              {result.ml_confidence !== null ? (
                <>
                  <div className="text-2xl font-bold text-cyan-400">{Math.round(result.ml_confidence * 100)}%</div>
                  <div className="text-xs text-gray-500 mt-1">ML model score</div>
                </>
              ) : (
                <>
                  <div className="text-2xl font-bold text-gray-600">—</div>
                  <div className="text-xs text-gray-600 mt-1">ML not trained yet</div>
                </>
              )}
            </div>
          </div>

          <button onClick={reset} className="w-full py-3 rounded-xl bg-white/5 hover:bg-white/10 text-gray-300 text-sm font-medium transition-colors border border-white/10">
            Analyze Another Video
          </button>
        </div>
      )}

      <p className="mt-16 text-gray-700 text-xs text-center max-w-sm">
        No video frames are decoded or stored. Detection reads file metadata only.
      </p>
    </main>
  );
}
