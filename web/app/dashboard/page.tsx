"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://ai-video-detector-production-a305.up.railway.app";

type Plan = { name: string; price: string; limit: string; tier: string; highlight?: boolean; features: string[] };

const PLANS: Plan[] = [
  {
    name: "Free",
    price: "$0",
    limit: "50 requests / month",
    tier: "free",
    features: ["File upload", "URL detection", "All platforms", "API access"],
  },
  {
    name: "Pro",
    price: "$9",
    limit: "1,000 requests / month",
    tier: "pro",
    highlight: true,
    features: ["Everything in Free", "Priority processing", "Batch detection", "Usage dashboard"],
  },
  {
    name: "Ultra",
    price: "$29",
    limit: "10,000 requests / month",
    tier: "ultra",
    features: ["Everything in Pro", "Webhook support", "SLA guarantee", "Dedicated support"],
  },
];

export default function Dashboard() {
  const [email, setEmail]       = useState("");
  const [apiKey, setApiKey]     = useState("");
  const [step, setStep]         = useState<"form" | "key" | "existing">("form");
  const [usage, setUsage]       = useState<any>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [copied, setCopied]     = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("upgraded") && params.get("email")) {
      setEmail(params.get("email")!);
      setStep("existing");
    }
  }, []);

  async function register() {
    if (!email.includes("@")) { setError("Enter a valid email"); return; }
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (data.api_key) {
        setApiKey(data.api_key);
        setStep("key");
      } else {
        setUsage(data);
        setStep("existing");
      }
    } catch {
      setError("Server error — try again");
    } finally {
      setLoading(false);
    }
  }

  async function upgrade(tier: string) {
    if (!email.includes("@")) { setError("Enter your email first"); return; }
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/upgrade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, tier }),
      });
      const data = await res.json();
      if (data.checkout_url) window.location.href = data.checkout_url;
      else throw new Error(data.detail || "Error");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function copy() {
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const [rotateInput, setRotateInput] = useState("");
  const [rotatedKey, setRotatedKey]   = useState("");
  const [rotateError, setRotateError] = useState("");
  const [rotating, setRotating]       = useState(false);

  const [usageKey, setUsageKey]       = useState("");
  const [usageData, setUsageData]     = useState<any>(null);
  const [usageError, setUsageError]   = useState("");
  const [usageLoading, setUsageLoading] = useState(false);

  async function checkUsage() {
    setUsageLoading(true);
    setUsageError("");
    setUsageData(null);
    try {
      const res = await fetch(`${API}/me`, { headers: { "X-Api-Key": usageKey.trim() } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Lookup failed");
      setUsageData(data);
    } catch (e: any) {
      setUsageError(e.message);
    } finally {
      setUsageLoading(false);
    }
  }

  async function rotate() {
    setRotating(true);
    setRotateError("");
    setRotatedKey("");
    try {
      const res = await fetch(`${API}/rotate-key`, {
        method: "POST",
        headers: { "X-Api-Key": rotateInput.trim() },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Rotation failed");
      setRotatedKey(data.api_key);
      setRotateInput("");
    } catch (e: any) {
      setRotateError(e.message);
    } finally {
      setRotating(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-14"
      style={{ background: "radial-gradient(ellipse at 50% 0%, #0d0d2b 0%, #07070f 60%)" }}>
      <div className="max-w-2xl mx-auto space-y-10">

        {/* Header */}
        <div className="text-center">
          <h1 className="text-4xl font-bold tracking-tight text-white mb-2">
            API Dashboard
          </h1>
          <p className="text-gray-500 text-sm">
            Integrate AI video detection into your own app
          </p>
        </div>

        {/* Pricing */}
        <div className="grid grid-cols-3 gap-3">
          {PLANS.map(plan => (
            <div key={plan.tier}
              className={`rounded-2xl p-5 border flex flex-col gap-4 ${
                plan.highlight
                  ? "border-violet-500/50 bg-violet-500/8"
                  : "border-white/8 bg-white/3"
              }`}>
              {plan.highlight && (
                <div className="text-xs font-bold text-violet-400 tracking-widest">POPULAR</div>
              )}
              <div>
                <div className="text-white font-bold text-lg">{plan.name}</div>
                <div className="text-2xl font-black text-white mt-1">
                  {plan.price}<span className="text-sm font-normal text-gray-500">/mo</span>
                </div>
                <div className="text-gray-600 text-xs mt-1">{plan.limit}</div>
              </div>
              <ul className="space-y-1.5 flex-1">
                {plan.features.map(f => (
                  <li key={f} className="text-gray-400 text-xs flex gap-2">
                    <span className="text-violet-400">✓</span>{f}
                  </li>
                ))}
              </ul>
              {plan.tier === "free" ? (
                <div className="text-xs text-gray-600 text-center">Register below ↓</div>
              ) : (
                <button
                  onClick={() => upgrade(plan.tier)}
                  disabled={loading}
                  className="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all hover:scale-105 disabled:opacity-40"
                  style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
                  Upgrade
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Register / Key display */}
        <div className="bg-white/3 border border-white/8 rounded-2xl p-6 space-y-4">

          {step === "form" && (
            <>
              <h2 className="text-white font-bold text-lg">Get your free API key</h2>
              <div className="flex gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && register()}
                  placeholder="your@email.com"
                  className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm placeholder-gray-600 outline-none focus:border-violet-500/60 transition-all"
                />
                <button
                  onClick={register}
                  disabled={loading}
                  className="px-6 py-3 rounded-xl text-sm font-semibold text-white disabled:opacity-40 hover:scale-105 transition-all"
                  style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
                  {loading ? "…" : "Get Key"}
                </button>
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
            </>
          )}

          {step === "key" && (
            <>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <h2 className="text-white font-bold">Your API key is ready</h2>
              </div>
              <div className="bg-black/40 border border-white/10 rounded-xl px-4 py-3 font-mono text-sm text-violet-300 break-all">
                {apiKey}
              </div>
              <button onClick={copy}
                className="text-sm text-gray-500 hover:text-white transition-colors flex items-center gap-2">
                {copied ? "✓ Copied!" : "📋 Copy to clipboard"}
              </button>
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 text-amber-300 text-xs">
                ⚠️ Save this key now — it won't be shown again.
              </div>
              <div className="pt-2">
                <p className="text-gray-500 text-xs mb-2">Usage example:</p>
                <pre className="bg-black/40 rounded-xl p-3 text-xs text-gray-400 overflow-x-auto">{`curl -X POST \\
  https://ai-video-detector-production-a305.up.railway.app/detect-url \\
  -H "X-Api-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"url":"https://www.tiktok.com/@user/video/123"}'`}</pre>
              </div>
            </>
          )}

          {step === "existing" && (
            <>
              <h2 className="text-white font-bold">Welcome back</h2>
              {usage && (
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Plan</span>
                    <span className="text-white font-semibold capitalize">{usage.tier}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Used this month</span>
                    <span className="text-white">{usage.requests_this_month} / {usage.monthly_limit}</span>
                  </div>
                  <div className="h-2 bg-white/8 rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-600 transition-all"
                      style={{ width: `${Math.min(100, (usage.requests_this_month / usage.monthly_limit) * 100)}%` }} />
                  </div>
                </div>
              )}
              <p className="text-gray-500 text-sm">
                Already have your key? Use it with the <code className="text-violet-400">X-Api-Key</code> header.
              </p>
            </>
          )}
        </div>

        {/* Usage: 30-day history */}
        <div className="rounded-2xl border border-white/8 bg-white/3 p-5 space-y-3">
          <h2 className="text-white font-bold text-sm">📊 Check your usage</h2>
          <p className="text-gray-500 text-xs">Paste your key to see this month&apos;s quota and the last 30 days. This check doesn&apos;t count against your quota.</p>
          <div className="flex gap-2">
            <input
              type="password"
              value={usageKey}
              onChange={e => { setUsageKey(e.target.value); setUsageError(""); }}
              placeholder="aivd_..."
              className="flex-1 bg-black/40 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white font-mono placeholder-gray-600 outline-none focus:border-violet-500/50"
            />
            <button
              onClick={checkUsage}
              disabled={usageLoading || !usageKey.trim()}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-40 transition-all"
              style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
              {usageLoading ? "Loading…" : "Show"}
            </button>
          </div>
          {usageError && <p className="text-red-400 text-xs">{usageError}</p>}
          {usageData && (
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Plan</span>
                <span className="text-white font-semibold capitalize">{usageData.tier}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">This month</span>
                <span className="text-white">{usageData.requests_this_month} / {usageData.monthly_limit}</span>
              </div>
              <div className="h-2 bg-white/8 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-600"
                  style={{ width: `${Math.min(100, (usageData.requests_this_month / usageData.monthly_limit) * 100)}%` }} />
              </div>
              {Array.isArray(usageData.usage_history) && (
                <div>
                  <p className="text-[11px] text-gray-500 mb-1.5">Last 30 days</p>
                  <div className="flex items-end gap-[2px] h-12">
                    {usageData.usage_history.map((d: { day: string; count: number }) => {
                      const max = Math.max(1, ...usageData.usage_history.map((x: any) => x.count));
                      return (
                        <div key={d.day} title={`${d.day}: ${d.count}`}
                          className="flex-1 rounded-t bg-violet-500/70 hover:bg-violet-400 transition-colors"
                          style={{ height: `${Math.max(4, (d.count / max) * 100)}%`, opacity: d.count === 0 ? 0.18 : 1 }} />
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Security: rotate a leaked key */}
        <div className="rounded-2xl border border-white/8 bg-white/3 p-5 space-y-3">
          <h2 className="text-white font-bold text-sm">🔐 Rotate your API key</h2>
          <p className="text-gray-500 text-xs">
            Leaked a key? Paste it here to replace the secret. Same plan and usage — the old key stops working immediately.
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={rotateInput}
              onChange={e => { setRotateInput(e.target.value); setRotateError(""); }}
              placeholder="aivd_..."
              className="flex-1 bg-black/40 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white font-mono placeholder-gray-600 outline-none focus:border-violet-500/50"
            />
            <button
              onClick={rotate}
              disabled={rotating || !rotateInput.trim()}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-40 transition-all"
              style={{ background: "linear-gradient(135deg, #4f46e5, #7c3aed)" }}>
              {rotating ? "Rotating…" : "Rotate"}
            </button>
          </div>
          {rotateError && <p className="text-red-400 text-xs">{rotateError}</p>}
          {rotatedKey && (
            <div className="space-y-2">
              <div className="bg-black/40 border border-green-500/25 rounded-xl px-4 py-3 font-mono text-sm text-green-300 break-all">
                {rotatedKey}
              </div>
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 text-amber-300 text-xs">
                ⚠️ Save the new key now — it won&apos;t be shown again. The old key is dead.
              </div>
            </div>
          )}
        </div>

        {/* Back link */}
        <div className="text-center">
          <a href="/" className="text-gray-600 hover:text-gray-400 text-sm transition-colors">
            ← Back to detector
          </a>
        </div>

      </div>
    </main>
  );
}
