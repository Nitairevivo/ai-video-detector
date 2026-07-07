export const metadata = { title: "Accuracy & Methodology — VerifAI" };

function Stat({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/3 p-5 text-center">
      <p className="text-3xl font-extrabold text-white">{value}</p>
      <p className="text-xs text-gray-400 mt-1.5">{label}</p>
      {note && <p className="text-[10px] text-gray-600 mt-1">{note}</p>}
    </div>
  );
}

export default function Accuracy() {
  return (
    <div className="min-h-screen text-gray-300" style={{ background: "#0a0a13" }}>
      <div className="max-w-2xl mx-auto px-6 py-16">
        <a href="/" className="text-sm text-violet-400 hover:text-violet-300">← VerifAI</a>
        <h1 className="text-3xl font-extrabold text-white mt-6 mb-2">Accuracy & Methodology</h1>
        <p className="text-xs text-gray-500 mb-10">
          We publish how the numbers are measured, not just the numbers. Last updated: July 2026.
        </p>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">Current model performance</h2>
          <p className="text-sm text-gray-400 leading-relaxed mb-4">
            Measured by stratified 5-fold cross-validation on 882 labeled videos
            (400 AI-generated / 482 real), out-of-fold predictions only — the model is
            never scored on a video it trained on. Probabilities are isotonic-calibrated.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat value="0.975" label="ROC AUC" />
            <Stat value="96.5%" label="Precision" note="flagged AI → really AI" />
            <Stat value="88.8%" label="Recall" note="AI videos caught" />
            <Stat value="2.7%" label="False-positive rate" note="real flagged as AI" />
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">What these numbers do and don&apos;t claim</h2>
          <ul className="text-sm text-gray-400 leading-relaxed space-y-2 list-disc pl-5">
            <li>
              They measure the <b className="text-gray-300">statistical signature model</b> — one layer of the stack.
              Hard evidence (a validly signed C2PA credential, a platform&apos;s own AI label, an
              AI tool&apos;s metadata signature) decides directly at 93–99% confidence and doesn&apos;t
              depend on this model at all.
            </li>
            <li>
              Cross-validation is honest but shares a collection distribution with training.
              A <b className="text-gray-300">blind real-world benchmark</b> (300 videos the system has never seen,
              collected across platforms, including deliberately hard cases like chaotic real
              footage and human CGI) is in progress; results will be published here.
            </li>
            <li>
              We bias against false positives by design: calibrated probabilities, a
              single-witness rule (one layer alone can&apos;t flip a verdict to AI), and a
              camera-origin guard. A confident &quot;AI&quot; from VerifAI is meant to be trustable.
            </li>
          </ul>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">The evidence stack</h2>
          <ol className="text-sm text-gray-400 leading-relaxed space-y-2 list-decimal pl-5">
            <li><b className="text-gray-300">File forensics</b> — cryptographic C2PA verification, AI-tool metadata, proprietary MP4 boxes, codec fingerprints.</li>
            <li><b className="text-gray-300">Platform intelligence</b> — TikTok AIGC, YouTube &quot;Altered or synthetic content&quot;, Meta &quot;AI info&quot; labels, read where they survive transcoding.</li>
            <li><b className="text-gray-300">Vision ensemble</b> — Gemini temporal-pair analysis fused in log-odds space with frame, frequency, motion and audio models.</li>
          </ol>
          <p className="text-xs text-gray-600 mt-3">
            Every API response includes an <code className="text-violet-400">explanation</code> object showing which
            layer decided and every layer&apos;s score — audit it yourself.
          </p>
        </section>

        <div className="flex gap-4 text-sm">
          <a href="/#upload" className="text-violet-400 hover:text-violet-300">Try it →</a>
          <a href="/privacy" className="text-gray-500 hover:text-gray-400">Privacy</a>
        </div>
      </div>
    </div>
  );
}
