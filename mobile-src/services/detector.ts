const API_BASE = "https://your-api-domain.com"; // change to your deployed API

export type DetectionResult = {
  is_ai_generated: boolean;
  confidence: number;
  confidence_pct: string;
  ai_tool_detected: string | null;
  detection_method: string;
};

export async function detectVideoFile(
  uri: string,
  filename: string
): Promise<DetectionResult> {
  const form = new FormData();
  form.append("file", {
    uri,
    name: filename,
    type: "video/mp4",
  } as unknown as Blob);

  const res = await fetch(`${API_BASE}/detect`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error ${res.status}`);
  }

  return res.json();
}

export async function detectVideoUrl(url: string): Promise<DetectionResult> {
  const res = await fetch(`${API_BASE}/detect-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error ${res.status}`);
  }

  return res.json();
}
