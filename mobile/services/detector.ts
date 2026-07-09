import * as FileSystem from "expo-file-system";

const API_BASE = "https://ai-video-detector-production-a305.up.railway.app";

export type DetectionResult = {
  is_ai_generated: boolean;
  verdict: "ai_generated" | "ai_edited" | "real";
  confidence: number;
  ai_tool_detected: string | null;
  edit_tool_detected: string | null;
  detection_method: string;
  mode?: string;  // "fast" (code-first, instant) | undefined (full)
  // Audit breakdown from the server: provenance flags + per-layer scores
  explanation?: {
    provenance?: {
      c2pa_present?: boolean;
      c2pa_claims_ai?: boolean;
      synthetic_media_marker?: boolean;
      iptc_digital_source_type?: string | null;
      camera_provenance?: boolean;
      metadata_stripped?: boolean;
      platform_reencoded?: boolean;
      platform_ai_label?: boolean;
      ai_tool?: string | null;
    };
    layer_scores?: Record<string, number>;
    frame_timeline?: number[];  // per-frame suspicion 0=natural … 1=AI-like
    caveats?: string[];
  } | null;
};

// Download video ON THE PHONE (residential IP → TikTok allows it)
// then upload to our API. This bypasses TikTok's datacenter IP block.
async function downloadAndDetect(url: string): Promise<DetectionResult> {
  const tmpPath = FileSystem.cacheDirectory + "verifai_tmp.mp4";

  // Remove old temp file
  try { await FileSystem.deleteAsync(tmpPath, { idempotent: true }); } catch {}

  // Download video from TikTok/Instagram/etc. using PHONE IP (not server IP)
  const downloadResult = await FileSystem.downloadAsync(url, tmpPath, {
    headers: {
      "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
      "Referer": new URL(url).origin,
    },
  });

  if (downloadResult.status !== 200) {
    throw new Error("Could not download video");
  }

  // Upload the file to API
  const uploadResult = await FileSystem.uploadAsync(`${API_BASE}/detect`, tmpPath, {
    httpMethod: "POST",
    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
    fieldName: "file",
    mimeType: "video/mp4",
    parameters: {},
  });

  // Cleanup
  try { await FileSystem.deleteAsync(tmpPath, { idempotent: true }); } catch {}

  if (uploadResult.status !== 200) {
    throw new Error(`Server error ${uploadResult.status}`);
  }

  return JSON.parse(uploadResult.body) as DetectionResult;
}

const TIKTOK_CDN_PATTERNS = [
  /tiktok\.com/,
  /vm\.tiktok\.com/,
  /instagram\.com/,
  /snapchat\.com/,
];

function needsPhoneDownload(url: string): boolean {
  return TIKTOK_CDN_PATTERNS.some((p) => p.test(url));
}

// Upload a local video file directly to /detect (bypasses URL IP blocking)
export async function detectVideoFileUpload(uri: string, mimeType = "video/mp4"): Promise<DetectionResult> {
  const form = new FormData();
  const filename = uri.split("/").pop() || "video.mp4";
  form.append("file", { uri, name: filename, type: mimeType } as unknown as Blob);
  const res = await fetch(`${API_BASE}/detect`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || `Server error ${res.status}`);
  }
  return res.json();
}

export async function detectVideoUrl(url: string): Promise<DetectionResult> {
  // For TikTok/Instagram: download on phone first, then upload
  // For YouTube/others: let server handle it (server can download those)
  if (needsPhoneDownload(url)) {
    try {
      return await downloadAndDetect(url);
    } catch {
      // Fallback to server-side if phone download fails
    }
  }

  // Server-side detection (works for YouTube, direct MP4 links, etc.)
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
