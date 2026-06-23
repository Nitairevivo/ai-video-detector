const API_BASE = "https://ai-video-detector-production-a305.up.railway.app";

export type DetectionResult = {
  is_ai_generated: boolean;
  verdict: "ai_generated" | "ai_edited" | "real";
  confidence: number;
  ai_tool_detected: string | null;
  edit_tool_detected: string | null;
  detection_method: string;
};

export async function detectVideoUrl(url: string): Promise<DetectionResult> {
  const res = await fetch(`${API_BASE}/detect-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || `Server error ${res.status}`);
  }
  return res.json();
}
