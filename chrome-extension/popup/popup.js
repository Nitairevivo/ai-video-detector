const API = "https://ai-video-detector-production-a305.up.railway.app";

const statusEl = document.getElementById("status");
const autoToggle = document.getElementById("autoAnalyze");
const urlInput = document.getElementById("urlInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const resultEl = document.getElementById("result");
const cacheCountEl = document.getElementById("cacheCount");

// ─── API health check ─────────────────────────────────────────────────────────

async function checkApi() {
  try {
    const res = await fetch(`${API}/`, { signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      statusEl.textContent = "● Online";
      statusEl.className = "status online";
    } else {
      throw new Error();
    }
  } catch {
    statusEl.textContent = "● Offline";
    statusEl.className = "status offline";
  }
}

// ─── Auto-analyze toggle ──────────────────────────────────────────────────────

chrome.storage.sync.get(["autoAnalyze"], ({ autoAnalyze }) => {
  autoToggle.checked = !!autoAnalyze;
});

autoToggle.addEventListener("change", () => {
  chrome.storage.sync.set({ autoAnalyze: autoToggle.checked });
  // Notify active tab to start/stop auto mode
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, {
        type: "SET_AUTO_ANALYZE",
        value: autoToggle.checked,
      }).catch(() => {});
    }
  });
});

// ─── URL analysis ─────────────────────────────────────────────────────────────

analyzeBtn.addEventListener("click", analyzeUrl);
urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") analyzeUrl(); });

async function analyzeUrl() {
  const url = urlInput.value.trim();
  if (!url || !url.startsWith("http")) {
    urlInput.style.borderColor = "#ef4444";
    setTimeout(() => (urlInput.style.borderColor = ""), 1500);
    return;
  }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "⏳";
  resultEl.className = "result hidden";

  try {
    const res = await fetch(`${API}/detect-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Error ${res.status}`);
    }

    const data = await res.json();
    showResult(data);
  } catch (e) {
    resultEl.className = "result ai";
    resultEl.innerHTML = `<span class="verdict">Error</span><span class="detail">${e.message}</span>`;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "→";
  }
}

function showResult(data) {
  const isAI = data.is_ai_generated;
  const pct = Math.round(data.confidence * 100);
  const tool = data.ai_tool_detected;

  resultEl.className = `result ${isAI ? "ai" : "real"}`;
  resultEl.innerHTML = `
    <span class="verdict">${isAI ? "⚠️ AI Generated" : "✅ Authentic"} · ${pct}%</span>
    ${tool ? `<span class="detail">Tool: <span class="tool">${tool}</span></span>` : ""}
    <span class="detail">${data.detection_method}</span>
  `;
}

// ─── Show how many results are cached in this session ─────────────────────────

chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
  if (!tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "GET_CACHE_COUNT" }, (count) => {
    if (chrome.runtime.lastError) return;
    if (typeof count === "number") {
      cacheCountEl.textContent = `${count} cached`;
    }
  });
});

// ─── Init ─────────────────────────────────────────────────────────────────────

checkApi();
