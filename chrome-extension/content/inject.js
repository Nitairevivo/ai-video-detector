const API = "https://ai-video-detector-production-a305.up.railway.app";

// ─── Cache ────────────────────────────────────────────────────────────────────
const CACHE_KEY = "verifai_cache_v2";
let resultCache = {};
chrome.storage.local.get([CACHE_KEY], (s) => { resultCache = s[CACHE_KEY] || {}; });

// ─── Platform ─────────────────────────────────────────────────────────────────
const PLATFORM = (() => {
  const h = location.hostname;
  if (h.includes("tiktok"))    return "tiktok";
  if (h.includes("instagram")) return "instagram";
  if (h.includes("youtube"))   return "youtube";
  if (h.includes("twitter") || h.includes("x.com")) return "twitter";
  if (h.includes("reddit"))    return "reddit";
  if (h.includes("facebook") || h.includes("fb.watch")) return "facebook";
  if (h.includes("snapchat"))  return "snapchat";
  if (h.includes("vimeo"))     return "vimeo";
  if (h.includes("twitch"))    return "twitch";
  if (h.includes("dailymotion")) return "dailymotion";
  return "unknown";
})();

const SELECTORS = {
  tiktok:      'div[class*="DivVideoContainer"], div[data-e2e="recommend-list-item-container"], article',
  instagram:   'article, div[role="dialog"]',
  youtube:     "ytd-reel-video-renderer, ytd-shorts, ytd-video-renderer, ytd-rich-item-renderer",
  twitter:     'article[data-testid="tweet"]',
  reddit:      'shreddit-post, div[data-testid="post-container"]',
  facebook:    'div[data-pagelet*="FeedUnit"], div[role="article"]',
  snapchat:    'div[class*="VideoPlayer"]',
  vimeo:       '.player_container',
  twitch:      '.video-player',
  dailymotion: '.player-root',
};

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
      if (location.pathname.startsWith("/shorts/") || location.pathname === "/watch") return location.href;
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
    default:
      return location.href;
  }
}

// ─── Verdict styles ───────────────────────────────────────────────────────────
function getVerdictStyle(result) {
  const v = result.verdict || (result.is_ai_generated ? "ai_generated" : "real");
  if (v === "ai_generated") return {
    color: "#ef4444", bg: "rgba(10,2,2,0.93)", border: "#ef444466",
    icon: "🤖", label: "AI GENERATED",
    title: result.ai_tool_detected ? `Made with ${result.ai_tool_detected}` : "AI-Generated Video",
  };
  if (v === "ai_edited") return {
    color: "#a855f7", bg: "rgba(8,2,14,0.93)", border: "#a855f766",
    icon: "✏️", label: "AI EDITED",
    title: result.edit_tool_detected ? `Edited with ${result.edit_tool_detected}` : "Real video, AI-edited",
  };
  return {
    color: "#22c55e", bg: "rgba(2,10,4,0.93)", border: "#22c55e66",
    icon: "✅", label: "AUTHENTIC",
    title: "Real Footage",
  };
}

// ─── Scan button ──────────────────────────────────────────────────────────────
function injectScanButton(container) {
  if (container._aivdBtn) return;
  container._aivdBtn = true;
  if (getComputedStyle(container).position === "static") container.style.position = "relative";

  const btn = document.createElement("div");
  btn.className = "aivd-scan-btn";
  btn.title = "VerifAI — Check this video";
  btn.innerHTML = `<span class="aivd-scan-icon">🔍</span><span class="aivd-scan-label">VerifAI</span>`;
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    e.preventDefault();
    await analyze(container, false);
  });
  container.appendChild(btn);
}

// ─── Loading / Result ─────────────────────────────────────────────────────────
function removeResult(container) {
  container.querySelector(".aivd-loader")?.remove();
  container.querySelector(".aivd-result")?.remove();
}

function injectLoader(container) {
  removeResult(container);
  const loader = document.createElement("div");
  loader.className = "aivd-loader";
  loader.innerHTML = `<span></span><span></span><span></span>`;
  container.appendChild(loader);
  return loader;
}

function showResult(container, result) {
  removeResult(container);
  const style = getVerdictStyle(result);
  const pct = Math.round(result.confidence * 100);

  const el = document.createElement("div");
  el.className = "aivd-result";
  el.style.cssText = `background:${style.bg};border-color:${style.border};`;
  el.innerHTML = `
    <div class="aivd-result-bar" style="background:${style.color}"></div>
    <div class="aivd-result-body">
      <div class="aivd-result-badge" style="color:${style.color};background:${style.color}22">${style.icon} ${style.label}</div>
      <div class="aivd-result-title">${style.title}</div>
      <div class="aivd-result-method">${(result.detection_method || "").slice(0, 60)}</div>
    </div>
    <div class="aivd-result-pct" style="color:${style.color}">${pct}%</div>
    <button class="aivd-result-close">✕</button>
  `;
  el.querySelector(".aivd-result-close").addEventListener("click", (e) => { e.stopPropagation(); el.remove(); });
  if (result.verdict !== "ai_generated") setTimeout(() => el.remove(), 8000);
  container.appendChild(el);
  container.querySelector(".aivd-scan-btn")?.remove();
}

// ─── Analyze ──────────────────────────────────────────────────────────────────
const analyzing = new Set();
let aiDetectedCount = 0;

async function analyze(container, auto = true) {
  const url = getVideoUrl(container);
  if (!url || analyzing.has(url)) return;
  if (resultCache[url]) { showResult(container, resultCache[url]); return; }

  analyzing.add(url);
  const loader = injectLoader(container);
  try {
    const response = await chrome.runtime.sendMessage({ type: "ANALYZE_URL", url });
    loader?.remove();
    if (response?.ok && response.result) {
      resultCache[url] = response.result;
      chrome.storage.local.set({ [CACHE_KEY]: resultCache });
      if (!auto || response.result.verdict !== "real") showResult(container, response.result);
      if (response.result.verdict === "ai_generated") {
        aiDetectedCount++;
        chrome.runtime.sendMessage({ type: "UPDATE_BADGE", count: aiDetectedCount }).catch(() => {});
      }
    } else { loader?.remove(); }
  } catch { loader?.remove(); }
  finally { analyzing.delete(url); }
}

// ─── Observer ─────────────────────────────────────────────────────────────────
let io = null, mo = null;

function startObserver() {
  if (io) return;
  const sel = SELECTORS[PLATFORM];
  if (!sel) return;
  io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const el = entry.target;
      injectScanButton(el);
      if (!el._aivdScanned) { el._aivdScanned = true; analyze(el, true); }
    }
  }, { threshold: 0.6 });
  const observe = (el) => { if (!el._aivdBtn) io.observe(el); };
  document.querySelectorAll(sel).forEach(observe);
  mo = new MutationObserver((mutations) => {
    for (const m of mutations)
      for (const node of m.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.matches?.(sel)) observe(node);
        node.querySelectorAll?.(sel).forEach(observe);
      }
  });
  mo.observe(document.body, { childList: true, subtree: true });
}

function stopObserver() { io?.disconnect(); io = null; mo?.disconnect(); mo = null; }

// ─── Messages ─────────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_STATS") sendResponse({ total: Object.keys(resultCache).length, ai: aiDetectedCount });
  if (msg.type === "SCAN_CURRENT") {
    const sel = SELECTORS[PLATFORM];
    const containers = sel ? [...document.querySelectorAll(sel)] : [];
    const visible = containers.find(c => {
      const r = c.getBoundingClientRect();
      return r.top >= 0 && r.bottom <= window.innerHeight + 100;
    }) || containers[0];
    if (visible) analyze(visible, false);
  }
  if (msg.type === "SET_AUTO_ANALYZE") msg.enabled ? startObserver() : stopObserver();
});

// ─── Init ─────────────────────────────────────────────────────────────────────
chrome.storage.sync.get(["autoAnalyze"], ({ autoAnalyze }) => {
  if (autoAnalyze !== false) startObserver();
});
