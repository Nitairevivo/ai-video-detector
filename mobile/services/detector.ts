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

// Upload a local video OR image file directly to /detect (bypasses URL IP
// blocking). The server routes by filename extension, so when a content:// URI
// has no extension we synthesise one from the mime type — otherwise an image
// would be misrouted as a video.
export async function detectVideoFileUpload(uri: string, mimeType = "video/mp4"): Promise<DetectionResult> {
  const form = new FormData();
  const raw = uri.split("/").pop() || "";
  let filename = raw;
  if (!/\.[a-z0-9]{2,4}$/i.test(raw)) {
    const isImg = mimeType.startsWith("image/");
    let ext = (mimeType.split("/")[1] || (isImg ? "jpg" : "mp4")).toLowerCase();
    if (ext === "jpeg") ext = "jpg";
    if (ext === "quicktime") ext = "mov";
    filename = `upload.${ext}`;
  }
  form.append("file", { uri, name: filename, type: mimeType } as unknown as Blob);
  const res = await fetch(`${API_BASE}/detect`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || `Server error ${res.status}`);
  }
  return res.json();
}

// A direct video FILE (…/x.mp4), as opposed to a platform *page* URL.
const DIRECT_FILE_RE = /\.(mp4|webm|mov|mkv|m4v)(\?|$)/i;
const PLATFORM_PAGE_RE = /(tiktok\.com|instagram\.com|facebook\.com|fb\.watch|twitter\.com|x\.com|snapchat\.com|pinterest\.com)/i;

const MOBILE_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1";

// The platform's own "AI-generated" disclosure, read straight from the page —
// definitive, and doesn't need the video at all. Anchored to JSON boundaries so
// a post merely *about* AI doesn't match.
const AIGC_PAGE_RE = [
  /"aigc_label_type"\s*:\s*[1-9]/i,
  /"aigcLabelType"\s*:\s*[1-9]/i,
  /"is_ai_generated"\s*:\s*true/i,
  /"content_check[^"]*"\s*:\s*\{[^}]*"ai[_-]?generated"\s*:\s*true/i,
  /"(?:label|text|displayText)"\s*:\s*"(?:Creator labeled as AI-generated|AI-generated|Made with AI)"/i,
];

// The real CDN video URL embedded in the page JSON.
const CDN_URL_RE = [
  /"playAddr":"([^"]+\.mp4[^"]*)"/i,
  /"downloadAddr":"([^"]+\.mp4[^"]*)"/i,
  /(https:\/\/[^"'\\\s]*tiktokcdn[^"'\\\s]+\.mp4[^"'\\\s]*)/i,
  /(https:\/\/[^"'\\\s]+\.mp4[^"'\\\s]*)/i,
];

// Fetch a platform PAGE on the phone's residential IP (not blocked like the
// server's datacenter IP), read the AI label, and pull the real video URL.
async function resolveOnPhone(url: string): Promise<{ aigc: boolean; cdnUrl: string | null }> {
  const resp = await fetch(url, {
    headers: { "User-Agent": MOBILE_UA, "Accept-Language": "en-US,en;q=0.9" },
  });
  const html = await resp.text();
  const aigc = AIGC_PAGE_RE.some((re) => re.test(html));
  let cdnUrl: string | null = null;
  for (const re of CDN_URL_RE) {
    const m = html.match(re);
    if (m && m[1]) { cdnUrl = m[1].replace(/\\u002F/gi, "/").replace(/\\\//g, "/").replace(/\\u0026/gi, "&"); break; }
  }
  return { aigc, cdnUrl };
}

export async function detectVideoUrl(url: string): Promise<DetectionResult> {
  // Direct video file → download on the phone and upload.
  if (DIRECT_FILE_RE.test(url)) {
    try { return await downloadAndDetect(url); } catch { /* fall through */ }
  }

  // Platform page → resolve on the phone (residential IP) first.
  if (PLATFORM_PAGE_RE.test(url)) {
    try {
      const { aigc, cdnUrl } = await resolveOnPhone(url);
      if (aigc) {
        return {
          is_ai_generated: true, verdict: "ai_generated", confidence: 0.97,
          ai_tool_detected: "Platform AI label", edit_tool_detected: null,
          detection_method: "Platform AI-disclosure label (read on device)",
          explanation: { provenance: { platform_ai_label: true } },
        };
      }
      if (cdnUrl) {
        try { return await downloadAndDetect(cdnUrl); } catch { /* fall through */ }
      }
    } catch { /* fall through to server */ }
  }

  // Fallback: let the server try (yt-dlp / resolver / direct).
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
