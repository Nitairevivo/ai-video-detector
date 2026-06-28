const API = "https://ai-video-detector-production-a305.up.railway.app";

// ─── Context menu ──────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "aivd-check-link",
    title: "Check if AI-generated",
    contexts: ["link", "video"],
  });
  chrome.contextMenus.create({
    id: "aivd-check-page",
    title: "Check this video page",
    contexts: ["page"],
    documentUrlPatterns: [
      "https://www.tiktok.com/*",
      "https://www.instagram.com/*/reel/*",
      "https://www.instagram.com/*/p/*",
      "https://www.youtube.com/shorts/*",
      "https://www.youtube.com/watch*",
      "https://twitter.com/*/status/*",
      "https://x.com/*/status/*",
    ],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.pageUrl || info.srcUrl;
  if (!url) return;

  // Show immediate notification that analysis started
  chrome.notifications.create("aivd-analyzing", {
    type: "basic",
    iconUrl: "icons/icon48.png",
    title: "AI Video Detector",
    message: "Analyzing video…",
    priority: 0,
  });

  try {
    const { deepAnalyze } = await chrome.storage.sync.get(["deepAnalyze"]);
    const result = await analyzeUrl(url, deepAnalyze === true);
    const pct = Math.round(result.confidence * 100);

    if (result.is_ai_generated) {
      const tool = result.ai_tool_detected ? ` · ${result.ai_tool_detected}` : "";
      chrome.notifications.create("aivd-result", {
        type: "basic",
        iconUrl: "icons/icon48.png",
        title: `🤖 AI-Generated (${pct}%)${tool}`,
        message: result.detection_method,
        priority: 2,
      });
    } else {
      chrome.notifications.create("aivd-result", {
        type: "basic",
        iconUrl: "icons/icon48.png",
        title: `✅ Authentic footage (${pct}% real)`,
        message: result.detection_method,
        priority: 1,
      });
    }

    // Forward result to content script so it can show badge
    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, {
        type: "SHOW_RESULT_FROM_CONTEXT",
        url,
        result,
      }).catch(() => {});
    }
  } catch (e) {
    chrome.notifications.create("aivd-error", {
      type: "basic",
      iconUrl: "icons/icon48.png",
      title: "AI Video Detector — Error",
      message: e.message || "Could not analyze this URL",
      priority: 1,
    });
  }
});

// ─── Messages from content script / popup ─────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_BADGE") {
    const label = msg.count > 0 ? String(msg.count) : "";
    const color = msg.count > 0 ? "#ef4444" : "#666";
    chrome.action.setBadgeText({ text: label, tabId: sender.tab?.id });
    chrome.action.setBadgeBackgroundColor({ color, tabId: sender.tab?.id });
    return;
  }

  if (msg.type === "ANALYZE_URL") {
    analyzeUrl(msg.url, msg.deep ?? false)
      .then(result => sendResponse({ ok: true, result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "ANALYZE_FILE") {
    analyzeBlob(msg.dataUrl, msg.filename)
      .then(result => sendResponse({ ok: true, result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

// ─── API calls ─────────────────────────────────────────────────────────────────

async function analyzeUrl(url, deep = false) {
  const res = await fetch(`${API}/detect-url?deep=${deep}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal: AbortSignal.timeout(50000), // 50s — gives yt-dlp time to download
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

async function analyzeBlob(dataUrl, filename) {
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
