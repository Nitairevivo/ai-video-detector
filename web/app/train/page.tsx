"use client";

import { useState, useRef, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type UploadItem = {
  id: string;
  file: File;
  label: "ai" | "real" | null;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
};

export default function TrainPage() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [training, setTraining] = useState(false);
  const [trainResult, setTrainResult] = useState<Record<string, unknown> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((files: FileList | File[]) => {
    const newItems: UploadItem[] = Array.from(files)
      .filter(f => /\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name))
      .map(f => ({
        id: Math.random().toString(36).slice(2),
        file: f,
        label: null,
        status: "pending",
      }));
    setItems(prev => [...prev, ...newItems]);
  }, []);

  const setLabel = (id: string, label: "ai" | "real") => {
    setItems(prev => prev.map(item => item.id === id ? { ...item, label } : item));
  };

  const removeItem = (id: string) => {
    setItems(prev => prev.filter(item => item.id !== id));
  };

  const uploadAll = async () => {
    const ready = items.filter(i => i.label && i.status === "pending");
    if (ready.length === 0) return;

    for (const item of ready) {
      setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "uploading" } : i));

      const form = new FormData();
      form.append("file", item.file);

      try {
        const res = await fetch(`${API}/label?is_ai=${item.label === "ai"}`, {
          method: "POST",
          body: form,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Upload failed");
        }
        setItems(prev => prev.map(i => i.id === item.id ? { ...i, status: "done" } : i));
      } catch (e: unknown) {
        setItems(prev => prev.map(i =>
          i.id === item.id ? { ...i, status: "error", error: e instanceof Error ? e.message : "Error" } : i
        ));
      }
    }
  };

  const trainModel = async () => {
    setTraining(true);
    setTrainResult(null);
    try {
      const res = await fetch(`${API}/train`, { method: "POST" });
      const data = await res.json();
      setTrainResult(data);
    } catch {
      setTrainResult({ error: "Failed to reach API" });
    } finally {
      setTraining(false);
    }
  };

  const doneCount = items.filter(i => i.status === "done").length;
  const readyCount = items.filter(i => i.label && i.status === "pending").length;
  const aiCount = items.filter(i => i.label === "ai").length;
  const realCount = items.filter(i => i.label === "real").length;

  return (
    <main
      className="min-h-screen px-4 py-12"
      style={{ background: "radial-gradient(ellipse at 50% 0%, #0d0d2b 0%, #07070f 60%)" }}
    >
      <div className="max-w-xl mx-auto space-y-6">

        {/* Header */}
        <div>
          <a href="/" className="text-xs text-gray-600 hover:text-gray-400 transition-colors">← Back to detector</a>
          <h1 className="text-3xl font-bold text-white mt-3 mb-1">Train the Model</h1>
          <p className="text-gray-400 text-sm">Upload videos, label them AI or Real, then train.</p>
        </div>

        {/* Stats bar */}
        {items.length > 0 && (
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white/3 border border-white/8 rounded-xl p-3 text-center">
              <div className="text-xl font-bold text-red-400">{aiCount}</div>
              <div className="text-xs text-gray-500">AI labeled</div>
            </div>
            <div className="bg-white/3 border border-white/8 rounded-xl p-3 text-center">
              <div className="text-xl font-bold text-green-400">{realCount}</div>
              <div className="text-xs text-gray-500">Real labeled</div>
            </div>
            <div className="bg-white/3 border border-white/8 rounded-xl p-3 text-center">
              <div className="text-xl font-bold text-violet-400">{doneCount}</div>
              <div className="text-xs text-gray-500">Uploaded</div>
            </div>
          </div>
        )}

        {/* Drop zone */}
        <div
          onClick={() => fileRef.current?.click()}
          onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
          onDragOver={e => e.preventDefault()}
          className="w-full h-36 rounded-2xl border-2 border-dashed border-white/15 bg-white/3
            hover:border-white/30 hover:bg-white/5 cursor-pointer transition-all
            flex flex-col items-center justify-center gap-2"
        >
          <div className="text-2xl">📁</div>
          <p className="text-white font-medium text-sm">Tap to add videos</p>
          <p className="text-gray-500 text-xs">MP4, MOV, MKV, WebM — multiple files OK</p>
          <input
            ref={fileRef}
            type="file"
            accept=".mp4,.mov,.mkv,.webm,.m4v"
            multiple
            className="hidden"
            onChange={e => e.target.files && addFiles(e.target.files)}
          />
        </div>

        {/* Video list */}
        {items.length > 0 && (
          <div className="space-y-2">
            {items.map(item => (
              <div key={item.id}
                className="bg-white/3 border border-white/8 rounded-xl p-3 flex items-center gap-3">

                {/* Status indicator */}
                <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0
                  bg-white/5 text-base">
                  {item.status === "done" ? "✅" :
                   item.status === "error" ? "❌" :
                   item.status === "uploading" ? "⏳" : "🎬"}
                </div>

                {/* Filename */}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-xs font-medium truncate">{item.file.name}</p>
                  <p className="text-gray-600 text-xs">
                    {(item.file.size / (1024 * 1024)).toFixed(1)} MB
                    {item.error && <span className="text-red-400 ml-2">{item.error}</span>}
                  </p>
                </div>

                {/* Label buttons */}
                {item.status === "pending" && (
                  <div className="flex gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => setLabel(item.id, "ai")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        item.label === "ai"
                          ? "bg-red-500 text-white"
                          : "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20"
                      }`}
                    >AI</button>
                    <button
                      onClick={() => setLabel(item.id, "real")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        item.label === "real"
                          ? "bg-green-500 text-white"
                          : "bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20"
                      }`}
                    >Real</button>
                    <button
                      onClick={() => removeItem(item.id)}
                      className="px-2 py-1.5 rounded-lg text-gray-600 hover:text-gray-400 text-xs transition-colors"
                    >✕</button>
                  </div>
                )}

                {item.status === "done" && (
                  <span className={`text-xs font-bold flex-shrink-0 ${
                    item.label === "ai" ? "text-red-400" : "text-green-400"
                  }`}>
                    {item.label === "ai" ? "AI ✓" : "Real ✓"}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Upload button */}
        {readyCount > 0 && (
          <button
            onClick={uploadAll}
            className="w-full py-3 rounded-xl bg-violet-600 hover:bg-violet-500
              text-white font-semibold text-sm transition-colors"
          >
            Upload {readyCount} labeled video{readyCount !== 1 ? "s" : ""}
          </button>
        )}

        {/* Train button */}
        <div className="bg-white/3 border border-white/8 rounded-2xl p-5 space-y-3">
          <div>
            <h2 className="text-white font-semibold mb-1">Train ML Model</h2>
            <p className="text-gray-500 text-xs">
              Needs at least 20 videos (10 AI + 10 Real) uploaded.
              More = better accuracy.
            </p>
          </div>

          <button
            onClick={trainModel}
            disabled={training}
            className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500
              disabled:bg-gray-800 disabled:text-gray-600
              text-white font-semibold text-sm transition-colors"
          >
            {training ? "Training..." : "🧠 Train Model"}
          </button>

          {trainResult && (
            <div className={`rounded-xl p-4 text-sm ${
              "error" in trainResult
                ? "bg-red-500/10 border border-red-500/20 text-red-400"
                : "bg-green-500/10 border border-green-500/20 text-green-400"
            }`}>
              {"error" in trainResult ? (
                <p>{String(trainResult.error)}</p>
              ) : (
                <div className="space-y-1">
                  <p className="font-bold text-green-300">✅ Model trained!</p>
                  <p>Samples: {String(trainResult.ai_samples)} AI + {String(trainResult.real_samples)} Real</p>
                  <p>Accuracy (AUC): <strong>{(Number(trainResult.cv_auc_mean) * 100).toFixed(1)}%</strong></p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Instructions */}
        <div className="bg-white/2 border border-white/6 rounded-2xl p-5 space-y-3">
          <h3 className="text-gray-300 font-semibold text-sm">Where to find videos</h3>
          <div className="space-y-2 text-xs text-gray-500">
            <div className="flex gap-2">
              <span className="text-red-400 font-bold flex-shrink-0">AI:</span>
              <span>TikTok #aiVideo · Twitter/X #SoraAI · Pika.art gallery · RunwayML gallery</span>
            </div>
            <div className="flex gap-2">
              <span className="text-green-400 font-bold flex-shrink-0">Real:</span>
              <span>Videos you filmed · Pexels.com/videos · Pixabay.com/videos · Coverr.co</span>
            </div>
            <p className="text-gray-600 pt-1">
              💡 Save videos directly without editing — raw files have more metadata signals.
            </p>
          </div>
        </div>

      </div>
    </main>
  );
}
