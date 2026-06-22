const API = "https://ai-video-detector-production-a305.up.railway.app";

const resultCache = new Map();

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

// ─── Selectors ────────────────────────────────────────────────────────────────

const SELECTORS = {
  tiktok:    'div[class*="DivVideoContainer"], div[data-e2e="recommend-list-item-container"], article',
  instagram: 'article, div[role="dialog"], div[class*="x1cy8zhl"]',
  youtube:   "ytd-reel-video-renderer, ytd-shorts, ytd-video-renderer",
  twitter:   'article[data-testid="tweet"]',
  reddit:    'shreddit-post, div[data-testid="post-container"]',
  facebook:  'div[data-pagelet*="FeedUnit"], div[role="article"]',
  telegram:  'div.message',
};

// ─── URL extraction ───────────────────────────────────────────────────────────

function getVideoUrl(container) {
  switch (PLATFORM) {
    case "tiktok": {
      // Prefer a direct /video/ link inside the container
      const link = container.querySelector('a[href*="/video/"]');
      if (link) return link.href;
      // Current page is a single video
      if (/\/@[^/]+\/video\/\d+/.test(location.pathname)) return location.href;
      // Feed — try to extract from data attributes
      const videoId = container.getAttribute("data-video-id") ||
                      container.querySelector("[data-video-id]")?.getAttribute("data-video-id");
      if (videoId) {
        const userLink = container.querySelector("a[href*='/@']");
        const user = userLink ? new URL(userLink.href).pathname : "/@unknown";
        return `https://www.tiktok.com${user}/video/${videoId}`;
      }
      return null; // don't fall back to generic feed URL
    }
    case "instagram": {
      const link = container.querySelector('a[href*="/reel/"], a[href*="/p/"], a[href*="/tv/"]');
      if (link) {
        const u = new URL(link.href);
        return "https://www.instagram.com" + u.pathname;
      }
      if (/\/(reel|p|tv)\//.test(location.pathname)) return location.href;
      return null;
    }
    case "youtube": {
      // Shorts — current page
      if (location.pathname.startsWith("/shorts/")) return location.href;
      // Regular watch page
      if (location.pathname === "/watch") return location.href;
      // In-feed short or video card
      const link = container.querySelector('a[href^="/shorts/"], a[href*="watch?v="]');
      if (link) {
        const u = new URL(link.href, "https://www.youtube.com");
        return u.href;
      }
      return null;
    }
    case "twitter": {
      // Look in the article for a status link with a video indicator
      const article = container.closest?.("article") || container;
      const link = article.querySelector('a[href*="/status/"]');
      if (link) return link.href;
      return null;
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
  // Non-blob video src as final fallback
  const video = container.querySelector("video");
  if (video?.src && !video.src.startsWith("blob:") && !video.src.startsWith("data:")) return video.src;
  return null;
}

// ─── Loading state injection ──────────────────────────────────────────────────

function injectLoader(container) {
  if (container._aivdInjected) return;
  container._aivdInjected = true;

  if (getComputedStyle(container).position === "static")
    container.style.position = "relative";

  const loader = document.createElement("div");
  loader.className = "aivd-loader";
  loader.innerHTML = `<span class="aivd-loader-dot"></span><span class="aivd-loader-dot"></span><span class="aivd-loader-dot"></span>`;
  container.appendChild(loader);
  return loader;
}

// ─── Analysis ─────────────────────────────────────────────────────────────────

async function analyze(container) {
  const url = getVideoUrl(container);
  if (!url) {
    container._aivdInjected = false; // allow retry
    return;
  }

  // Return cached result instantly
  if (resultCache.has(url)) {
    const cached = resultCache.get(url);
    if (cached.is_ai_generated) showAIBadge(container, cached);
    return;
  }

  const loader = injectLoader(container);

  let response;
  try {
    response = await chrome.runtime.sendMessage({ type: "ANALYZE_URL", url });
  } catch {
    loader?.remove();
    container._aivdInjected = false;
    return;
  }

  loader?.remove();

  if (!response?.ok) return; // silent fail — don't mark as anything

  resultCache.set(url, response.result);

  // Only show badge if AI — real videos stay clean
  if (response.result.is_ai_generated) {
    aiDetectedCount++;
    showAIBadge(container, response.result);
  }
}

// ─── AI Badge ─────────────────────────────────────────────────────────────────

function showAIBadge(container, result) {
  // Don't double-inject
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

  // Tooltip on hover
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
  badge.addEventListener("mouseleave", () => {
    badge.querySelector(".aivd-tip")?.remove();
  });

  // Click to dismiss
  badge.addEventListener("click", (e) => { e.stopPropagation(); badge.remove(); });

  container.appendChild(badge);
}

// Stats tracking
let aiDetectedCount = 0;

// Handle messages from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_STATS") {
    sendResponse({ total: resultCache.size, ai: aiDetectedCount });
  }
  if (msg.type === "SET_AUTO_ANALYZE") {
    location.reload();
  }
});

// ─── Observer ─────────────────────────────────────────────────────────────────

function init() {
  const sel = SELECTORS[PLATFORM];
  if (!sel) return;

  // IntersectionObserver: analyze when video enters viewport
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting && !entry.target._aivdInjected) {
        analyze(entry.target);
      }
    }
  }, { threshold: 0.5 });

  const observe = (el) => { if (!el._aivdInjected) io.observe(el); };

  document.querySelectorAll(sel).forEach(observe);

  new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.matches?.(sel)) observe(node);
        node.querySelectorAll?.(sel).forEach(observe);
      }
    }
  }).observe(document.body, { childList: true, subtree: true });
}

init();
