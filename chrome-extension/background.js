const API = "https://ai-video-detector-production-a305.up.railway.app";

// Receives requests from content script to analyze a video URL
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ANALYZE_URL") {
    analyzeUrl(msg.url)
      .then(result => sendResponse({ ok: true, result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true; // keep channel open for async response
  }

  if (msg.type === "ANALYZE_FILE") {
    // For direct video file blobs passed from content script
    analyzeBlob(msg.dataUrl, msg.filename)
      .then(result => sendResponse({ ok: true, result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

async function analyzeUrl(url) {
  const res = await fetch(`${API}/detect-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

async function analyzeBlob(dataUrl, filename) {
  // Convert base64 data URL back to blob
  const response = await fetch(dataUrl);
  const blob = await response.blob();

  const form = new FormData();
  form.append("file", blob, filename || "video.mp4");

  const res = await fetch(`${API}/detect`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}
