const API = "https://ai-video-detector-production-a305.up.railway.app";

// Persistent cache — survives page refreshes
const CACHE_KEY = "aivd_cache";
let resultCache = {};
chrome.storage.local.get([CACHE_KEY], (s) => { resultCache = s[CACHE_KEY] || {}; });

const PLATFORM = (() => {
  const h = location.hostname;
  if (h.includes("tiktok"))    return "tiktok";
  if (h.includes("instagram")) return "instagram";
  if (h.includes("youtube"))   return "youtube";
  if (h.includes("twitter") || h.includes("x.com")) return "twitter";
  if (h.includes("reddit"))    return "reddit";
  if (h.includes("facebook") || h.includes("fb.watch")) return "facebook";
  if (h.includes("t.me"))      return "telegram";
  return "unknown";
})();

// ─── Selectors ─────────────────────────────────────────────────────────────────

const SELECTORS = {
  tiktok:    'div[class*="DivVideoContainer"], div[data-e2e="recommend-list-item-container"], article',
  instagram: 'article, div[role="dialog"], div[class*="x1cy8zhl"]',
  youtube:   "ytd-reel-video-renderer, ytd-shorts, ytd-video-renderer, ytd-rich-item-renderer",
  twitter:   'article[data-testid="tweet"]',
  reddit:    'shreddit-post, div[data-testid="post-container"]',
  facebook:  'div[data-pagelet*="FeedUnit"], div[role="article"]',
  telegram:  'div.message',
};

// ─── URL extraction ────────────────────────────────────────────────────────────

function getVideoUrl(container) {
  switch (PLATFORM) {
    case "tiktok": {
      const link = container.querySelector('a[href*="/video/"]');
      if (link) return link.href;
      if (/\/@[^/]+\/video\/\d+/.test(location.pathname)) return location.href;
      const videoId = container.getAttribute("data-video-id") ||
                      container.querySelector("[data-video-id]")?.getAttribute("data-video-id");
      if (videoId) {
        const userLink = container.querySelector("a[href*='/@']");
        const user = userLink ? new URL(userLink.href).pathname : "/@unknown";
        return `https://www.tiktok.com${user}/video/${videoId}`;
      }
      return null;
    }
    case "instagram": {
      const link = container.querySelector('a[href*="/reel/"], a[href*="/p/"], a[href*="/tv/"]');
      if (link) return "https://www.instagram.com" + new URL(link.href).pathname;
      if (/\/(reel|p|tv)\//.test(location.pathname)) return location.href;
      return null;
    }
    case "youtube": {
      if (location.pathname.startsWith("/shorts/")) return location.href;
      if (location.pathname === "/watch") return location.href;
      const link = container.querySelector('a[href^="/shorts/"], a[href*="watch?v="]');
      if (link) return new URL(link.href, "https://www.youtube.com").href;
      return null;
    }
    case "twitter": {
      const article = container.closest?.("article") || container;
      const link = article.querySelector('a[href*="/status/"]');
      return link ? link.href : null;
    }
    case "reddit": {
      const link = container.querySelector('a[href*="/comments/"]');
      if (link) return link.href;
      if (location.pathname.includes("/comments/")) return location.href;
      return null;
    }
    case "facebook": {
      const link = container.querySelector('a[href*="/watch/"], a[href*="/reel/"], a[href*="videos/"]');
      if (link) return link.href;
      if (/\/(watch|reel|videos)/.test(location.pathname)) return location.href;
      return null;
    }
  }
  const video = container.querySelector("video");
  if (video?.src && !video.src.startsWith("blob:") && !video.src.startsWith("data:")) return video.src;
  return null;
}

// ─── Loading state ─────────────────────────────────────────────────────────────

function injectLoader(container) {
  if (container._aivdInjected) return null;
  container._aivdInjected = true;
  if (getComputedStyle(container).position === "static") container.style.position = "relative";
  const loader = document.createElement("div");
  loader.className = "aivd-loader";
  loader.innerHTML = `<span class="aivd-loader-dot"></span><span class="aivd-loader-dot"></span><span class="aivd-loader-dot"></span>`;
  container.appendChild(loader);
  return loader;
}

// ─── Analysis ──────────────────────────────────────────────────────────────────

async function analyze(container, deep = false) {
  const url = getVideoUrl(container);
  if (!url) { container._aivdInjected = false; return; }

  // Serve from persistent cache
  if (resultCache[url]) {
    if (resultCache[url].is_ai_generated) showBadge(container, resultCache[url]);
    return;
  }

  const loader = injectLoader(container);

  let response;
  try {
    response = await chrome.runtime.sendMessage({ type: "ANALYZE_URL", url, deep });
  } catch {
    loader?.remove();
    container._aivdInjected = false;
    return;
  }

  loader?.remove();
  if (!response?.ok) return;

  // Persist result
  resultCache[url] = response.result;
  chrome.storage.local.set({ [CACHE_KEY]: resultCache });

  if (response.result.is_ai_generated) {
    aiDetectedCount++;
    updateBadgeCount();
    showBadge(container, response.result);
  }
}

// ─── Badge ─────────────────────────────────────────────────────────────────────

function showBadge(container, result) {
  if (container.querySelector(".aivd-badge")) return;
  const pct  = Math.round(result.confidence * 100);
  const tool = result.ai_tool_detected;

  const badge = document.createElement("div");
  badge.className = "aivd-badge";
  badge.innerHTML = `
    <svg class="aivd-icon" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/>
      <path d="M5 8.5l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <span class="aivd-label">AI${tool ? ` · ${tool}` : ""}</span>
    <span class="aivd-pct">${pct}%</span>
  `;

  badge.addEventListener("mouseenter", () => {
    const tip = document.createElement("div");
    tip.className = "aivd-tip";
    tip.innerHTML = `
      <div class="aivd-tip-title">🤖 AI-Generated Video</div>
      <div class="aivd-tip-row"><span>Confidence</span><strong>${pct}%</strong></div>
      ${tool ? `<div class="aivd-tip-row"><span>Tool</span><strong>${tool}</strong></div>` : ""}
      <div class="aivd-tip-method">${result.detection_method}</div>
    `;
    badge.appendChild(tip);
  });
  badge.addEventListener("mouseleave", () => badge.querySelector(".aivd-tip")?.remove());
  badge.addEventListener("click", (e) => { e.stopPropagation(); badge.remove(); });

  container.appendChild(badge);
}

// ─── Extension badge count ─────────────────────────────────────────────────────

let aiDetectedCount = 0;

function updateBadgeCount() {
  chrome.runtime.sendMessage({
    type: "UPDATE_BADGE",
    count: aiDetectedCount,
  }).catch(() => {});
}

// ─── Messages ──────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_STATS") {
    sendResponse({ total: Object.keys(resultCache).length, ai: aiDetectedCount });
  }
  if (msg.type === "SET_AUTO_ANALYZE") {
    // Don't reload — just toggle observer
    if (msg.enabled) startObserver();
    else stopObserver();
  }
  // Result injected from context-menu check in background.js
  if (msg.type === "SHOW_RESULT_FROM_CONTEXT") {
    const container = document.querySelector(SELECTORS[PLATFORM]);
    if (container && msg.result?.is_ai_generated) showBadge(container, msg.result);
  }
});

// ─── Observer ──────────────────────────────────────────────────────────────────

let io = null;
let mo = null;

function startObserver() {
  if (io) return; // already running
  const sel = SELECTORS[PLATFORM];
  if (!sel) return;

  chrome.storage.sync.get(["deepAnalyze"], ({ deepAnalyze }) => {
    const deep = deepAnalyze === true;

    io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && !entry.target._aivdInjected) {
          analyze(entry.target, deep);
        }
      }
    }, { threshold: 0.5 });

    const observe = (el) => { if (!el._aivdInjected) io.observe(el); };
    document.querySelectorAll(sel).forEach(observe);

    mo = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of m.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches?.(sel)) observe(node);
          node.querySelectorAll?.(sel).forEach(observe);
        }
      }
    });
    mo.observe(document.body, { childList: true, subtree: true });
  });
}

function stopObserver() {
  io?.disconnect(); io = null;
  mo?.disconnect(); mo = null;
}

// ─── Init ──────────────────────────────────────────────────────────────────────

chrome.storage.sync.get(["autoAnalyze"], ({ autoAnalyze }) => {
  // Default on; only skip if explicitly disabled
  if (autoAnalyze !== false) startObserver();
});
