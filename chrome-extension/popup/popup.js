const API = "https://ai-video-detector-production-a305.up.railway.app";

const statusEl    = document.getElementById("status");
const statusText  = document.getElementById("statusText");
const autoToggle  = document.getElementById("autoAnalyze");
const deepToggle  = document.getElementById("deepAnalyze");
const urlInput    = document.getElementById("urlInput");
const analyzeBtn  = document.getElementById("analyzeBtn");
const resultEl    = document.getElementById("result");
const cacheCount  = document.getElementById("cacheCount");
const aiCount     = document.getElementById("aiCount");
const aiFoundStat = document.getElementById("aiFoundStat");

// ─── API health check ─────────────────────────────────────────────────────────

async function checkApi() {
  try {
    const res = await fetch(`${API}/`, { signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      statusEl.className = "status online";
      statusText.textContent = "Online";
    } else throw new Error();
  } catch {
    statusEl.className = "status offline";
    statusText.textContent = "Offline";
  }
}

// ─── Toggles ──────────────────────────────────────────────────────────────────

chrome.storage.sync.get(["autoAnalyze", "deepAnalyze"], ({ autoAnalyze, deepAnalyze }) => {
  autoToggle.checked = autoAnalyze !== false;
  deepToggle.checked = deepAnalyze === true;
});

autoToggle.addEventListener("change", () => {
  chrome.storage.sync.set({ autoAnalyze: autoToggle.checked });
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: "SET_AUTO_ANALYZE" }).catch(() => {});
  });
});

deepToggle.addEventListener("change", () => {
  chrome.storage.sync.set({ deepAnalyze: deepToggle.checked });
  // Show warning when enabling — deep mode is slower
  if (deepToggle.checked) {
    const tip = document.createElement("div");
    tip.className = "deep-tip";
    tip.textContent = "Deep mode adds ~10s per video";
    deepToggle.closest(".toggle-row").appendChild(tip);
    setTimeout(() => tip.remove(), 3000);
  }
});

// ─── Stats from active tab ────────────────────────────────────────────────────

chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
  if (!tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: "GET_STATS" }, (stats) => {
    if (chrome.runtime.lastError || !stats) return;
    cacheCount.textContent = stats.total ?? 0;
    if (stats.ai > 0) {
      aiCount.textContent = stats.ai;
      aiFoundStat.style.display = "flex";
    }
  });
});

// ─── URL analysis ─────────────────────────────────────────────────────────────

analyzeBtn.addEventListener("click", analyzeUrl);
urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") analyzeUrl(); });

// Auto-paste from clipboard on popup open
(async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text?.startsWith("http") && !urlInput.value) urlInput.value = text;
  } catch {}
})();

async function analyzeUrl() {
  const url = urlInput.value.trim();
  if (!url.startsWith("http")) {
    urlInput.style.borderColor = "#ef4444";
    setTimeout(() => urlInput.style.borderColor = "", 1500);
    return;
  }

  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5" stroke="white" stroke-width="1.5" stroke-dasharray="20" stroke-dashoffset="20" fill="none"><animate attributeName="stroke-dashoffset" from="20" to="0" dur="0.6s" repeatCount="indefinite"/></circle></svg>`;
  resultEl.className = "result hidden";

  // Show extra loading message for deep mode
  const isDeep = deepToggle.checked;
  if (isDeep) {
    resultEl.className = "result hidden";
    resultEl.innerHTML = `<span class="detail" style="color:#a78bfa">Running deep analysis — visual + frequency scan…</span>`;
    resultEl.className = "result";
  }

  try {
    const res = await fetch(`${API}/detect-url?deep=${isDeep}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Error ${res.status}`);
    }
    showResult(await res.json());
  } catch (e) {
    resultEl.className = "result ai";
    resultEl.innerHTML = `<span class="verdict">⚠️ Error</span><span class="detail">${e.message}</span>`;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" transform="rotate(45 7 7)"/></svg>`;
  }
}

function showResult(data) {
  const isAI  = data.is_ai_generated;
  const pct   = Math.round(data.confidence * 100);
  const tool  = data.ai_tool_detected;
  const deep  = data.deep_analysis_ran;

  resultEl.className = `result ${isAI ? "ai" : "real"}`;
  resultEl.innerHTML = `
    <span class="verdict">${isAI ? "🤖 AI Generated" : "✅ Authentic Footage"} · ${pct}%</span>
    ${tool ? `<span class="detail">Tool: <span class="tool">${tool}</span></span>` : ""}
    <span class="detail">${data.detection_method}</span>
    ${deep ? `<span class="detail" style="color:#a78bfa;font-size:10px">Deep analysis included</span>` : ""}
    <div class="conf-bar"><div class="conf-fill" style="width:${pct}%"></div></div>
  `;
}

checkApi();
