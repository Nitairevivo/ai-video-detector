/**
 * Content script — runs inside TikTok, Instagram, YouTube, Twitter, Reddit.
 *
 * Strategy per platform:
 *  - TikTok / Instagram Reels: observe video elements, extract src or page URL
 *  - YouTube Shorts: use current page URL directly
 *  - Twitter/X: extract video tweet URL
 *  - Reddit: extract video post URL
 *
 * For each video container found, we inject an "AI?" button.
 * Clicking it sends the URL to our background service worker → API.
 */

const API_HOST = "https://ai-video-detector-production-a305.up.railway.app";

// Cache results so we don't re-analyze the same URL
const resultCache = new Map();

// ─── Platform detection ───────────────────────────────────────────────────────

const PLATFORM = (() => {
  const h = location.hostname;
  if (h.includes("tiktok")) return "tiktok";
  if (h.includes("instagram")) return "instagram";
  if (h.includes("youtube")) return "youtube";
  if (h.includes("twitter") || h.includes("x.com")) return "twitter";
  if (h.includes("reddit")) return "reddit";
  return "unknown";
})();

// ─── Video container selectors per platform ───────────────────────────────────

const SELECTORS = {
  tiktok: 'div[class*="DivVideoContainer"], article',
  instagram: 'div[role="dialog"], article, div[class*="x1cy8zhl"]',
  youtube: "ytd-reel-video-renderer, ytd-shorts",
  twitter: 'div[data-testid="videoPlayer"]',
  reddit: 'div[data-testid="post-container"], shreddit-post',
};

// ─── URL extraction per platform ─────────────────────────────────────────────

function getVideoUrl(container) {
  // 1. Look for a <video> with a real src (not blob:)
  const video = container.querySelector("video");
  if (video?.src && !video.src.startsWith("blob:")) {
    return video.src;
  }

  // 2. Platform-specific page URL extraction
  switch (PLATFORM) {
    case "tiktok": {
      // TikTok embeds the video ID in the URL
      const link = container.querySelector('a[href*="/video/"]');
      if (link) return link.href;
      // Or the current page itself is a video
      if (location.href.includes("/video/")) return location.href;
      break;
    }
    case "instagram": {
      // Reels: current URL is the reel
      if (location.href.includes("/reel/") || location.href.includes("/p/")) {
        return location.href;
      }
      break;
    }
    case "youtube": {
      // Shorts
      if (location.href.includes("/shorts/")) return location.href;
      break;
    }
    case "twitter": {
      const link = container.closest('article')?.querySelector('a[href*="/status/"]');
      if (link) return link.href;
      break;
    }
    case "reddit": {
      const link = container.querySelector('a[href*="/comments/"]');
      if (link) return link.href;
      if (location.href.includes("/comments/")) return location.href;
      break;
    }
  }

  // 3. Fallback: use current page URL
  return location.href;
}

// ─── Button injection ─────────────────────────────────────────────────────────

function injectButton(container) {
  if (container._aivdInjected) return;
  container._aivdInjected = true;

  // Container must be positioned for absolute children
  const pos = getComputedStyle(container).position;
  if (pos === "static") container.style.position = "relative";

  const btn = document.createElement("div");
  btn.className = "aivd-btn";
  btn.innerHTML = `<span class="aivd-btn-dot"></span><span>AI?</span>`;
  btn.title = "Check if this video is AI-generated";

  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    e.preventDefault();
    await analyze(container, btn);
  });

  container.appendChild(btn);
}

async function analyze(container, btn) {
  const url = getVideoUrl(container);
  if (!url) return;

  // Return cached result instantly
  if (resultCache.has(url)) {
    showResult(container, btn, resultCache.get(url));
    return;
  }

  // Show loading state
  btn.innerHTML = `<span class="aivd-btn-dot loading"></span><span>Checking...</span>`;

  const response = await chrome.runtime.sendMessage({ type: "ANALYZE_URL", url });

  if (!response.ok) {
    btn.innerHTML = `<span class="aivd-btn-dot" style="background:#ef4444"></span><span>Error</span>`;
    setTimeout(() => {
      btn.innerHTML = `<span class="aivd-btn-dot"></span><span>AI?</span>`;
    }, 3000);
    return;
  }

  resultCache.set(url, response.result);
  showResult(container, btn, response.result);
}

function showResult(container, btn, result) {
  // Remove the "AI?" button
  btn.remove();

  const isAI = result.is_ai_generated;
  const pct = Math.round(result.confidence * 100);
  const tool = result.ai_tool_detected;

  const badge = document.createElement("div");
  badge.className = `aivd-result ${isAI ? "ai" : "real"}`;
  badge.innerHTML = `
    <span class="aivd-result-dot"></span>
    <span>${isAI ? (tool ? `AI · ${tool}` : "AI") : "Real"} ${pct}%</span>
  `;

  let tooltip = null;

  badge.addEventListener("mouseenter", () => {
    tooltip = document.createElement("div");
    tooltip.className = "aivd-tooltip";
    tooltip.innerHTML = `
      <strong>${isAI ? "⚠️ AI-Generated" : "✅ Authentic Footage"}</strong><br>
      Confidence: <strong>${pct}%</strong><br>
      ${tool ? `Tool: <span class="aivd-tool">${tool}</span><br>` : ""}
      Method: ${result.detection_method}
    `;
    container.appendChild(tooltip);
  });

  badge.addEventListener("mouseleave", () => {
    tooltip?.remove();
    tooltip = null;
  });

  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    // Re-analyze on click
    badge.remove();
    injectButton(container);
  });

  container.appendChild(badge);
}

// Handle messages from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_CACHE_COUNT") {
    sendResponse(resultCache.size);
  }
  if (msg.type === "SET_AUTO_ANALYZE") {
    // Reload page to apply auto-analyze change (simplest approach)
    location.reload();
  }
});

// ─── Observer — watches for new video containers as user scrolls ──────────────

function observeNewVideos() {
  const selector = SELECTORS[PLATFORM];
  if (!selector) return;

  // Inject on already-present containers
  document.querySelectorAll(selector).forEach(injectButton);

  // Watch for new ones added to DOM (infinite scroll)
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.matches?.(selector)) injectButton(node);
        node.querySelectorAll?.(selector).forEach(injectButton);
      }
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

// ─── Auto-analyze mode (optional, off by default) ────────────────────────────

chrome.storage.sync.get(["autoAnalyze"], ({ autoAnalyze }) => {
  observeNewVideos();

  if (autoAnalyze) {
    // Auto-trigger analysis on every new video that scrolls into view
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const container = entry.target;
        const btn = container.querySelector(".aivd-btn");
        if (btn) analyze(container, btn);
      }
    }, { threshold: 0.8 });

    const sel = SELECTORS[PLATFORM];
    if (sel) {
      document.querySelectorAll(sel).forEach(el => observer.observe(el));
      new MutationObserver((mutations) => {
        for (const m of mutations) {
          for (const node of m.addedNodes) {
            if (node instanceof Element && node.matches?.(sel)) {
              observer.observe(node);
            }
          }
        }
      }).observe(document.body, { childList: true, subtree: true });
    }
  }
});
