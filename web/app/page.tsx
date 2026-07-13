"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import IosInstallHint from "./IosInstallHint";

const HISTORY_KEY = "aivd_history";
const MAX_HISTORY = 50;

const API = process.env.NEXT_PUBLIC_API_URL || "https://ai-video-detector-production-a305.up.railway.app";

type Explanation = {
  deciding_layer?: string;
  layer_scores?: Record<string, number>;
  ml_probability?: number | null;
  provenance?: {
    c2pa_present?: boolean;
    c2pa_claims_ai?: boolean;
    synthetic_media_marker?: boolean;
    iptc_digital_source_type?: string | null;
    camera_provenance?: boolean;
    metadata_stripped?: boolean;
    platform_reencoded?: boolean;
    ai_tool?: string | null;
    edit_tool?: string | null;
  };
  visual_artifacts?: string[];
  frame_timeline?: number[];
  caveats?: string[];
};

type DetectionResult = {
  filename?: string;
  url?: string;
  is_ai_generated: boolean;
  verdict: "ai_generated" | "ai_edited" | "real";
  confidence: number;
  ai_tool_detected: string | null;
  edit_tool_detected: string | null;
  detection_method: string;
  gemini_reason?: string;
  explanation?: Explanation;
  signals?: Record<string, number>;
};

const LAYER_LABELS: Record<string, string> = {
  gemini: "AI Vision (Gemini)",
  metadata: "File metadata",
  frame_ml: "Frame model",
  visual: "Visual analysis",
  audio: "Audio fingerprint",
  ml: "Signature model",
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
    color: "#ff5470", bg: "rgba(255,84,112,0.06)", border: "rgba(255,84,112,0.28)",
    badge: "bg-[#ff5470]/15 text-[#ff97a8]", dot: "bg-[#ff5470]",
    label: "AI GENERATED", icon: "🤖",
    title: r.ai_tool_detected ? `Made with ${r.ai_tool_detected}` : "AI-Generated Video",
  };
  if (v === "ai_edited") return {
    color: "#b98bff", bg: "rgba(185,139,255,0.06)", border: "rgba(185,139,255,0.28)",
    badge: "bg-[#b98bff]/15 text-[#d3bcff]", dot: "bg-[#b98bff]",
    label: "AI EDITED", icon: "✏️",
    title: r.edit_tool_detected ? `Edited with ${r.edit_tool_detected}` : "Real Video, AI-Edited",
  };
  return {
    color: "#34e0a1", bg: "rgba(52,224,161,0.06)", border: "rgba(52,224,161,0.28)",
    badge: "bg-[#34e0a1]/15 text-[#8ff0cd]", dot: "bg-[#34e0a1]",
    label: "AUTHENTIC", icon: "✅",
    title: "Real Footage",
  };
}

// ── Logo ─────────────────────────────────────────────────────────────────────
function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="12" fill="url(#lg)" />
      <rect width="40" height="40" rx="12" fill="url(#lgloss)" />
      {/* bold verify check */}
      <path d="M11 20.5 L17.5 27.5 L29.5 12"
        stroke="white" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
      {/* cyan spark at the tip */}
      <circle cx="29.5" cy="12" r="2.7" fill="#22e3ee" />
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7c3aed" />
          <stop offset="0.5" stopColor="#d946ef" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
        <linearGradient id="lgloss" x1="0" y1="0" x2="0" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="white" stopOpacity="0.22" />
          <stop offset="0.5" stopColor="white" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ── Confidence ring ───────────────────────────────────────────────────────────
function ConfidenceMeter({ value, color }: { value: number; color: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="relative w-[92px] h-[92px] flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="7" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="7"
          strokeLinecap="round" strokeDasharray={`${2.51 * pct} 251`}
          style={{ transition: "stroke-dasharray 1s cubic-bezier(0.22,1,0.36,1)", filter: `drop-shadow(0 0 6px ${color}66)` }} />
      </svg>
      <div className="text-center z-10">
        <div className="text-xl font-bold tabular-nums" style={{ color }}>{pct}<span className="text-xs">%</span></div>
        <div className="text-[8px] uppercase tracking-widest text-faint mt-0.5">confidence</div>
      </div>
    </div>
  );
}

// ── Result card ───────────────────────────────────────────────────────────────
function ResultCard({ item, onRemove, onRetry }: { item: VideoItem; onRemove: () => void; onRetry?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const r = item.result;

  async function sendFeedback(userSaysAi: boolean) {
    if (!r || feedbackSent) return;
    setFeedbackSent(true);
    try {
      await fetch(`${API}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          verdict: r.verdict,
          confidence: r.confidence,
          user_says_ai: userSaysAi,
          method: r.detection_method?.slice(0, 200) || "",
          source: "web",
          signals: r.signals || null,
        }),
      });
    } catch { /* best-effort */ }
  }

  if (item.status === "analyzing") {
    return (
      <div className="card p-5 flex items-center gap-4 rise-in">
        <div className="relative w-11 h-11 rounded-xl bg-[#a066ff]/10 border border-[#a066ff]/25 flex items-center justify-center flex-shrink-0 overflow-hidden">
          <div className="absolute left-0 right-0 h-[2px] bg-[#a066ff] scan-beam" style={{ boxShadow: "0 0 10px #a066ff" }} />
          <svg className="w-5 h-5 text-[#a066ff] animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium truncate">{item.label}</p>
          <p className="text-faint text-xs mt-0.5 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#a066ff] animate-pulse inline-block" />
            {item.file ? `Reading the code · ${(item.file.size/1024/1024).toFixed(1)} MB` : "Reading the code behind it…"}
          </p>
        </div>
      </div>
    );
  }

  if (item.status === "error") {
    return (
      <div className="rounded-[22px] border border-[#ff5470]/25 bg-[#ff5470]/5 p-5 flex items-center gap-4 rise-in">
        <div className="w-11 h-11 rounded-xl bg-[#ff5470]/10 flex items-center justify-center flex-shrink-0 text-lg">⚠</div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium truncate">{item.label}</p>
          <p className="text-[#ff97a8] text-xs mt-0.5">{item.error}</p>
          {onRetry && (
            <button onClick={onRetry} className="text-xs text-[#a066ff] hover:text-[#a99bff] mt-1.5 transition-colors underline underline-offset-2">
              Try again
            </button>
          )}
        </div>
        <button onClick={onRemove} className="text-faint hover:text-white text-sm px-2 transition-colors">✕</button>
      </div>
    );
  }

  if (!r) return null;
  const style = getVerdictStyle(r);

  return (
    <div className="rounded-[22px] overflow-hidden transition-all duration-300 rise-in" style={{ background: style.bg, border: `1px solid ${style.border}` }}>
      <div style={{ height: 3, background: `linear-gradient(90deg, ${style.color}, transparent)` }} />
      <div className="p-5 flex items-center gap-4">
        <ConfidenceMeter value={r.confidence} color={style.color} />
        <div className="flex-1 min-w-0">
          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide mb-2 ${style.badge}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
            {style.icon} {style.label}
          </div>
          <p className="text-white font-semibold text-sm">{style.title}</p>
          <p className="text-muted text-xs mt-0.5 truncate">{item.label}</p>
          <p className="text-faint text-xs mt-1 truncate">{r.detection_method}</p>
          <div className="flex items-center flex-wrap gap-3 mt-2.5">
            {(r.signals || r.explanation) && (
              <button onClick={() => setExpanded(v => !v)} className="text-xs text-muted hover:text-white transition-colors font-medium">
                {expanded ? "Hide forensics ↑" : "Show forensics ↓"}
              </button>
            )}
            {item.url && (
              <button onClick={() => {
                const pct = Math.round(r.confidence * 100);
                const verdict = r.verdict === "ai_generated" ? "🤖 AI Generated" : r.verdict === "ai_edited" ? "✏️ AI Edited" : "✅ Real";
                navigator.clipboard.writeText(`${verdict} (${pct}%) — ${item.url}\nDetected by VerifAI`);
              }} className="text-xs text-muted hover:text-[#a066ff] transition-colors">
                Copy result
              </button>
            )}
            {feedbackSent ? (
              <span className="text-xs text-[#34e0a1]/90">✓ Thanks!</span>
            ) : (
              <span className="text-xs text-faint flex items-center gap-1.5">
                Right?
                <button onClick={() => sendFeedback(r.verdict === "ai_generated" || r.verdict === "ai_edited")}
                  className="hover:text-[#34e0a1] transition-colors" title="The verdict is correct">👍</button>
                <button onClick={() => sendFeedback(!(r.verdict === "ai_generated" || r.verdict === "ai_edited"))}
                  className="hover:text-[#ff5470] transition-colors" title="The verdict is wrong">👎</button>
              </span>
            )}
          </div>
        </div>
        <button onClick={onRemove} className="text-faint hover:text-white text-sm px-1 flex-shrink-0 transition-colors self-start">✕</button>
      </div>

      {expanded && (
        <div className="px-5 pb-5 border-t border-white/5 pt-4 space-y-4">
          {r.explanation?.layer_scores && Object.keys(r.explanation.layer_scores).length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-faint font-semibold mb-2">Detection layers</p>
              <div className="space-y-2">
                {Object.entries(r.explanation.layer_scores).map(([key, val]) => {
                  const pct = Math.round((val as number) * 100);
                  const barColor = pct >= 60 ? "#ff5470" : pct <= 40 ? "#34e0a1" : "#eab308";
                  return (
                    <div key={key} className="flex items-center gap-3 text-xs">
                      <span className="text-muted w-36 flex-shrink-0 truncate">{LAYER_LABELS[key] ?? key.replace(/_/g, " ")}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-white/8 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor, transition: "width .6s ease" }} />
                      </div>
                      <span className="mono font-semibold w-10 text-right" style={{ color: barColor }}>{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {r.explanation?.provenance && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-faint font-semibold mb-2">Provenance — the file&apos;s own code</p>
              <div className="flex flex-wrap gap-1.5">
                {r.explanation.provenance.c2pa_claims_ai && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-[#ff5470]/15 text-[#ff97a8] border border-[#ff5470]/25">🔏 C2PA: AI-generated (signed)</span>
                )}
                {r.explanation.provenance.c2pa_present && !r.explanation.provenance.c2pa_claims_ai && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-white/8 text-gray-300 border border-white/15">🔏 C2PA credentials present</span>
                )}
                {r.explanation.provenance.synthetic_media_marker && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-[#ff5470]/15 text-[#ff97a8] border border-[#ff5470]/25">
                    🏷 IPTC: {r.explanation.provenance.iptc_digital_source_type || "synthetic media"}
                  </span>
                )}
                {r.explanation.provenance.ai_tool && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-[#ff5470]/15 text-[#ff97a8] border border-[#ff5470]/25">🛠 {r.explanation.provenance.ai_tool}</span>
                )}
                {r.explanation.provenance.camera_provenance && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-[#34e0a1]/15 text-[#8ff0cd] border border-[#34e0a1]/25">📷 Camera capture (IPTC)</span>
                )}
                {r.explanation.provenance.metadata_stripped && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-yellow-500/10 text-yellow-300 border border-yellow-500/25">⚠ Metadata stripped</span>
                )}
                {r.explanation.provenance.platform_reencoded && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-yellow-500/10 text-yellow-300 border border-yellow-500/25">♻ Platform re-encoded</span>
                )}
                {!r.explanation.provenance.c2pa_present && !r.explanation.provenance.ai_tool &&
                 !r.explanation.provenance.synthetic_media_marker && !r.explanation.provenance.camera_provenance &&
                 !r.explanation.provenance.metadata_stripped && !r.explanation.provenance.platform_reencoded && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] bg-white/8 text-muted border border-white/15">No provenance markers</span>
                )}
              </div>
            </div>
          )}

          {r.explanation?.visual_artifacts && r.explanation.visual_artifacts.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-faint font-semibold mb-2">Visual artifacts spotted</p>
              <div className="flex flex-wrap gap-1.5">
                {r.explanation.visual_artifacts.map((a, i) => (
                  <span key={`${a}-${i}`} className="px-2 py-0.5 rounded-full text-[11px] bg-orange-500/10 text-orange-300 border border-orange-500/25">👁 {a}</span>
                ))}
              </div>
            </div>
          )}

          {r.explanation?.frame_timeline && r.explanation.frame_timeline.length > 1 && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-faint font-semibold mb-2">Frame timeline</p>
              <div className="flex items-end gap-[3px] h-16">
                {r.explanation.frame_timeline.map((v, i) => {
                  const pct = Math.max(4, Math.round(v * 100));
                  const c = v >= 0.6 ? "#ff5470" : v <= 0.4 ? "#34e0a1" : "#eab308";
                  return (
                    <div key={i} className="flex-1 flex flex-col justify-end group relative" title={`Frame ${i + 1}: ${Math.round(v * 100)}% AI-like`}>
                      <div className="w-full rounded-sm" style={{ height: `${pct}%`, background: c, transition: "height .6s ease" }} />
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] text-faint mt-1">
                <span>start</span>
                <span>sampled frames · red = most AI-like</span>
                <span>end</span>
              </div>
            </div>
          )}

          {r.explanation?.caveats && r.explanation.caveats.length > 0 && (
            <div className="text-[11px] text-yellow-400/80 space-y-0.5">
              {r.explanation.caveats.map((c, i) => <p key={`${c}-${i}`}>⚠ {c}</p>)}
            </div>
          )}

          {r.signals && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-faint font-semibold mb-2">Raw signals</p>
              <div className="space-y-1.5">
                {Object.entries(r.signals).filter(([,v]) => typeof v === "number").slice(0, 12).map(([key, val]) => (
                  <div key={key} className="flex justify-between items-center text-xs">
                    <span className="text-muted">{key.replace(/_/g, " ")}</span>
                    <span className="mono font-semibold text-gray-400">
                      {val === 1 ? "✓ YES" : val === 0 ? "— NO" : (val as number).toFixed(3)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Layer card (how it works) ──────────────────────────────────────────────────
function LayerCard({ n, title, desc, icon, accent }: { n: string; title: string; desc: string; icon: string; accent: string }) {
  return (
    <div className="card gborder p-6 relative overflow-hidden group hover:-translate-y-1 transition-transform duration-300">
      <div className="absolute -top-8 -right-8 w-28 h-28 rounded-full blur-3xl opacity-20 group-hover:opacity-40 transition-opacity" style={{ background: accent }} />
      <div className="flex items-center justify-between mb-4">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl" style={{ background: `${accent}1a`, border: `1px solid ${accent}44` }}>{icon}</div>
        <span className="mono text-xs text-faint">0{n}</span>
      </div>
      <p className="text-white font-semibold text-base mb-1.5">{title}</p>
      <p className="text-muted text-[13px] leading-relaxed">{desc}</p>
    </div>
  );
}

// ── Platform icons ────────────────────────────────────────────────────────────
const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "🎵", instagram: "📸", youtube: "▶️", twitter: "𝕏", x: "𝕏",
  reddit: "🤖", facebook: "👤", telegram: "✈️",
};
function getPlatformLabel(url: string) {
  try {
    const host = new URL(url).hostname.replace("www.", "");
    return `${PLATFORM_ICONS[host.split(".")[0]] ?? "🔗"} ${host}`;
  } catch { return url.slice(0, 60); }
}

const DETECTED_TOOLS = [
  "Sora", "Veo 3", "Kling", "Runway", "Midjourney", "Pika", "Luma",
  "Stable Diffusion", "Firefly", "DALL·E", "Flux", "Ideogram", "Hailuo", "Grok",
];

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Home() {
  const [items, setItems] = useState<VideoItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [deepMode, setDeepMode] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<Array<{url: string; label: string; verdict: string; confidence: number; tool: string | null; date: string}>>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(HISTORY_KEY);
      if (saved) setHistory(JSON.parse(saved));
    } catch {}
  }, []);

  const downloadAndDetect = useCallback(async (url: string, signal: AbortSignal, deep = false): Promise<Response> => {
    const isDirect = /\.(mp4|webm|mov|mkv|m4v)(\?|$)/i.test(url);
    if (isDirect) {
      try {
        const videoRes = await fetch(url, { signal, mode: "cors" });
        if (videoRes.ok) {
          const blob = await videoRes.blob();
          if (blob.size > 50000 && blob.type.includes("video")) {
            const form = new FormData();
            form.append("file", blob, "video.mp4");
            return fetch(`${API}/detect?deep=${deep}`, { method: "POST", body: form, signal });
          }
        }
      } catch { /* CORS block — fall through */ }
    }
    return fetch(`${API}/detect-url?deep=${deep}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal,
    });
  }, []);

  const analyzeItem = useCallback(async (item: VideoItem, deep = false) => {
    setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "analyzing" } : i));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), deep ? 180_000 : 120_000);
    try {
      let res: Response;
      if (item.url) {
        res = await downloadAndDetect(item.url, controller.signal, deep);
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
  }, [downloadAndDetect]);

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
    const valid = Array.from(files).filter(f => /\.(mp4|mov|mkv|webm|m4v|jpg|jpeg|png|webp|gif|bmp|tiff?|heic|heif|avif)$/i.test(f.name));
    const newItems: VideoItem[] = valid.map(f => ({ id: Math.random().toString(36).slice(2), file: f, label: f.name, status: "pending" as const }));
    setItems(prev => [...newItems, ...prev]);
    newItems.forEach(item => analyzeItem(item, deepMode));
  }, [analyzeItem, deepMode]);

  const aiCount = items.filter(i => i.result?.verdict === "ai_generated").length;
  const editedCount = items.filter(i => i.result?.verdict === "ai_edited").length;
  const realCount = items.filter(i => i.result?.verdict === "real").length;
  const analyzingCount = items.filter(i => i.status === "analyzing").length;
  const urlCount = urlInput.split(/[\n,\s]+/).filter(s => s.trim().startsWith("http")).length;

  return (
    <div className="min-h-screen flex flex-col relative" style={{ background: "radial-gradient(ellipse at 50% -12%, #1c0a44 0%, #0a0522 42%, #060314 72%)" }}>
      <div className="aurora" aria-hidden><span className="spark" /></div>
      <div className="fixed inset-0 z-0 grid-texture pointer-events-none" aria-hidden />
      <div className="grain" aria-hidden />
      <IosInstallHint />
      <div className="relative z-10 flex flex-col min-h-screen">

      {/* Navbar */}
      <nav className="flex items-center justify-between px-5 sm:px-8 py-4 border-b border-white/6 backdrop-blur-xl sticky top-0 z-50 bg-[#060314]/70">
        <a href="/" className="flex items-center gap-2.5">
          <Logo size={32} />
          <span className="font-bold text-lg tracking-tight">Verif<span className="text-[#a066ff]">AI</span></span>
        </a>
        <div className="flex items-center gap-1 sm:gap-3 text-sm">
          <a href="/accuracy" className="px-3 py-1.5 rounded-lg text-muted hover:text-white hover:bg-white/5 transition-colors hidden sm:block">Accuracy</a>
          <a href="#how" className="px-3 py-1.5 rounded-lg text-muted hover:text-white hover:bg-white/5 transition-colors hidden sm:block">How it works</a>
          <a href="/dashboard" className="px-3 py-1.5 rounded-lg text-muted hover:text-white hover:bg-white/5 transition-colors hidden sm:block">API</a>
          <a href="#detect" className="btn-ghost px-4 py-1.5 rounded-full text-[#c9c3ff] text-sm">
            Detect now
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex flex-col items-center text-center px-4 pt-16 sm:pt-24 pb-12">
        <div className="rise-in inline-flex items-center gap-2 glass rounded-full px-4 py-1.5 text-xs text-[#c9c3ff] mb-8">
          <span className="relative w-1.5 h-1.5 rounded-full bg-[#34e0a1] text-[#34e0a1] ping-soft" />
          Live model · self-improves every night · ships to production automatically
        </div>

        <div className="rise-in d1 mb-7 animate-float glow-pulse"><Logo size={88} /></div>

        <h1 className="rise-in d1 display text-[3.5rem] sm:text-[5.5rem] lg:text-[7rem] mb-5">
          <span className="text-white">Is it real,</span><br />
          <span className="shimmer-text">or is it AI?</span>
        </h1>

        <p className="rise-in d2 text-muted text-base sm:text-lg max-w-xl mx-auto mb-9 leading-relaxed">
          VerifAI doesn&apos;t guess from pixels — it <span className="text-white font-medium">reads the code behind the file</span>:
          cryptographic C2PA credentials, the platforms&apos; own AI labels, and a calibrated vision
          ensemble — even after TikTok, Instagram and X strip the metadata.
        </p>

        <div className="rise-in d3 flex flex-col sm:flex-row items-center gap-3 mb-10">
          <a href="#detect" className="btn-primary px-8 py-3.5 rounded-2xl font-semibold text-white text-sm">
            Detect a video or image →
          </a>
          <a href="/accuracy" className="btn-ghost px-6 py-3.5 rounded-2xl font-medium text-[#c9c3ff] text-sm">
            0% false positives on real footage
          </a>
        </div>

        {/* Verdict pills */}
        <div className="rise-in d4 flex flex-wrap items-center justify-center gap-2.5">
          <span className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[13px] text-[#ff97a8]" style={{ background: "rgba(255,84,112,0.08)", border: "1px solid rgba(255,84,112,0.22)" }}>🤖 AI Generated</span>
          <span className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[13px] text-[#d3bcff]" style={{ background: "rgba(185,139,255,0.08)", border: "1px solid rgba(185,139,255,0.22)" }}>✏️ AI Edited</span>
          <span className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[13px] text-[#8ff0cd]" style={{ background: "rgba(52,224,161,0.08)", border: "1px solid rgba(52,224,161,0.22)" }}>✅ Authentic</span>
        </div>
      </section>

      {/* Detected-tools marquee */}
      <section className="pb-14 pt-2">
        <p className="text-center text-[11px] uppercase tracking-[0.2em] text-faint mb-5">Catches output from 30+ generators</p>
        <div className="marquee-mask overflow-hidden">
          <div className="marquee gap-3">
            {[...DETECTED_TOOLS, ...DETECTED_TOOLS].map((t, i) => (
              <span key={i} className="glass rounded-xl px-4 py-2 text-sm text-gray-300 whitespace-nowrap flex-shrink-0">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="py-16 sm:py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-xs text-[#a066ff] font-bold tracking-[0.2em] uppercase mb-3">How it works</p>
            <h2 className="display text-3xl sm:text-5xl font-extrabold gradient-text">Evidence first. Vision second.</h2>
            <p className="text-muted text-sm mt-4 max-w-md mx-auto">Hard, verifiable evidence decides in milliseconds. The vision ensemble is the fallback — so a single layer can never cry wolf alone.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <LayerCard n="1" icon="🔏" accent="#a066ff" title="File forensics"
              desc="Cryptographically verifies C2PA Content Credentials and reads AI-tool signatures, proprietary MP4 boxes and codec fingerprints from Sora, Kling, Runway, Veo and 30+ tools." />
            <LayerCard n="2" icon="🏷️" accent="#22d3ee" title="Platform intelligence"
              desc="When platforms re-encode and strip the file, VerifAI reads their own AI-disclosure labels — TikTok AIGC, YouTube ‘Altered or synthetic’, Meta ‘AI info’ — straight from the source." />
            <LayerCard n="3" icon="👁️" accent="#34e0a1" title="Vision ensemble"
              desc="Gemini temporal-pair analysis fused with a frame model, frequency/motion analysis and audio fingerprinting — calibrated so no single layer decides alone." />
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-12 px-4 border-y border-white/7" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-6 text-center">
          <div><p className="display text-4xl sm:text-5xl font-extrabold gradient-text">30+</p><p className="text-xs text-muted mt-2">AI tools detected</p></div>
          <div><p className="display text-4xl sm:text-5xl font-extrabold gradient-text">6</p><p className="text-xs text-muted mt-2">detection layers</p></div>
          <a href="/accuracy" className="group"><p className="display text-4xl sm:text-5xl font-extrabold gradient-text group-hover:opacity-80 transition-opacity">0.98</p><p className="text-xs text-muted mt-2 group-hover:text-[#a066ff] transition-colors">cross-validated AUC ↗</p></a>
          <div><p className="display text-4xl sm:text-5xl font-extrabold gradient-text">~5s</p><p className="text-xs text-muted mt-2">avg detection time</p></div>
        </div>
      </section>

      {/* Detect */}
      <section id="detect" className="flex-1 px-4 py-16">
        <div className="max-w-2xl mx-auto space-y-5">
          <div className="text-center mb-8">
            <h2 className="display text-3xl sm:text-4xl font-bold text-white mb-2">Check any media</h2>
            <p className="text-muted text-sm">Paste a TikTok / Instagram / YouTube / X link, or drop a file</p>
          </div>

          {/* Deep mode toggle */}
          <div className="card flex items-center justify-between px-4 py-3.5">
            <div>
              <p className="text-sm font-semibold text-white">Deep Analysis</p>
              <p className="text-xs text-faint mt-0.5">Visual + frequency scan — catches re-encoded AI videos (~10s extra)</p>
            </div>
            <button
              onClick={() => setDeepMode(d => !d)}
              aria-label="Toggle deep analysis"
              className={`relative w-11 h-6 rounded-full transition-all duration-200 flex-shrink-0 ${deepMode ? "bg-[#a066ff]" : "bg-white/10"}`}>
              <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all duration-200 ${deepMode ? "left-5" : "left-0.5"}`} />
            </button>
          </div>

          {/* URL input */}
          <div className="space-y-2">
            <textarea
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); addUrls(urlInput); }
              }}
              placeholder={"Paste one or multiple links (TikTok, Instagram, YouTube, X…)\nOne per line for batch analysis"}
              rows={urlInput.split("\n").length > 1 ? Math.min(urlInput.split("\n").length + 1, 5) : 1}
              className="w-full px-4 py-3.5 rounded-2xl bg-white/5 border border-white/10 text-white text-sm placeholder-faint focus:outline-none focus:border-[#a066ff]/60 focus:ring-2 focus:ring-[#a066ff]/20 transition-all resize-none leading-relaxed"
            />
            <div className="flex gap-2">
              <button onClick={() => addUrls(urlInput)}
                disabled={urlCount === 0}
                className="btn-primary flex-1 py-3 rounded-2xl text-sm font-semibold text-white transition-all disabled:opacity-30 disabled:hover:translate-y-0">
                {urlCount > 1 ? `Detect ${urlCount} items` : "Detect"}
              </button>
              {history.length > 0 && (
                <button onClick={() => setShowHistory(v => !v)}
                  className="px-4 py-3 rounded-2xl text-sm font-medium border border-white/10 text-muted hover:text-white hover:border-white/20 transition-all">
                  {showHistory ? "Hide" : `History (${history.length})`}
                </button>
              )}
            </div>
          </div>

          {/* History panel */}
          {showHistory && history.length > 0 && (
            <div className="card overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/6">
                <span className="text-xs font-bold text-muted uppercase tracking-wider">Recent checks</span>
                <button onClick={() => { setHistory([]); localStorage.removeItem(HISTORY_KEY); }} className="text-xs text-faint hover:text-[#ff5470] transition-colors">Clear</button>
              </div>
              <div className="divide-y divide-white/5 max-h-64 overflow-y-auto">
                {history.map((h, i) => {
                  const color = h.verdict === "ai_generated" ? "#ff5470" : h.verdict === "ai_edited" ? "#b98bff" : "#34e0a1";
                  const icon = h.verdict === "ai_generated" ? "🤖" : h.verdict === "ai_edited" ? "✏️" : "✅";
                  return (
                    <button key={i} onClick={() => { setUrlInput(h.url); setShowHistory(false); }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/4 transition-colors text-left">
                      <span className="text-base flex-shrink-0">{icon}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-white truncate">{h.label}</p>
                        <p className="text-[10px] text-faint truncate">{h.url}</p>
                      </div>
                      <span className="text-xs font-bold flex-shrink-0" style={{ color }}>{Math.round(h.confidence * 100)}%</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 text-xs text-faint">
            <div className="flex-1 h-px bg-white/8" /><span>or upload a file</span><div className="flex-1 h-px bg-white/8" />
          </div>

          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => { e.preventDefault(); setIsDragging(false); addFiles(e.dataTransfer.files); }}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            className={`w-full h-48 rounded-3xl border-2 border-dashed cursor-pointer flex flex-col items-center justify-center gap-3 transition-all duration-200 ${
              isDragging ? "border-[#a066ff] bg-[#a066ff]/10 scale-[1.01]" : "border-white/12 bg-white/2 hover:border-[#a066ff]/50 hover:bg-white/4"
            }`}>
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl btn-primary">🎬</div>
            <div className="text-center">
              <p className="text-white font-semibold text-sm">Drop video or image here</p>
              <p className="text-faint text-xs mt-0.5">Video: MP4 · MOV · WebM &nbsp;·&nbsp; Image: JPG · PNG · WebP · HEIC</p>
            </div>
            <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.m4v,.jpg,.jpeg,.png,.webp,.gif,.bmp,.tif,.tiff,.heic,.heif,.avif" multiple className="hidden"
              onChange={e => e.target.files && addFiles(e.target.files)} />
          </div>

          {/* Summary bar */}
          {items.length > 0 && (
            <div className="flex items-center justify-between text-sm">
              <div className="flex gap-4 flex-wrap">
                {analyzingCount > 0 && <span className="text-[#a066ff] font-medium">⏳ {analyzingCount} analyzing</span>}
                {aiCount > 0 && <span className="text-[#ff5470] font-medium">🤖 {aiCount} AI</span>}
                {editedCount > 0 && <span className="text-[#b98bff] font-medium">✏️ {editedCount} Edited</span>}
                {realCount > 0 && <span className="text-[#34e0a1] font-medium">✅ {realCount} Real</span>}
              </div>
              <button onClick={() => setItems([])} className="text-xs text-faint hover:text-white transition-colors">
                Clear all
              </button>
            </div>
          )}

          {/* Results */}
          <div className="space-y-3">
            {items.map(item => (
              <ResultCard key={item.id} item={item}
                onRemove={() => setItems(prev => prev.filter(i => i.id !== item.id))}
                onRetry={() => analyzeItem({ ...item }, deepMode)} />
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/6 py-8 px-4">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-faint">
          <div className="flex items-center gap-2">
            <Logo size={20} />
            <span className="font-semibold text-muted">VerifAI</span>
            <span>· No files stored · Privacy safe</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="/accuracy" className="hover:text-white transition-colors">Accuracy</a>
            <a href="/privacy" className="hover:text-white transition-colors">Privacy</a>
            <a href="/dashboard" className="hover:text-white transition-colors">API</a>
            <span>Powered by Gemini Vision</span>
          </div>
        </div>
      </footer>
      </div>{/* end z-10 wrapper */}
    </div>
  );
}
