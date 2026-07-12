export const metadata = { title: "Accuracy & Methodology — VerifAI" };

function Stat({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div className="card gborder p-5 text-center">
      <p className="display text-3xl font-extrabold gradient-text">{value}</p>
      <p className="text-xs text-muted mt-1.5">{label}</p>
      {note && <p className="text-[10px] text-faint mt-1">{note}</p>}
    </div>
  );
}

export default function Accuracy() {
  return (
    <div className="min-h-screen relative" style={{ background: "radial-gradient(ellipse at 50% -10%, #180a3a 0%, #05050f 55%)" }}>
      <div className="aurora" aria-hidden><span className="spark" /></div>
      <div className="fixed inset-0 z-0 grid-texture pointer-events-none" aria-hidden />
      <div className="grain" aria-hidden />
      <div className="relative z-10 max-w-2xl mx-auto px-6 py-16 text-gray-300">
        <a href="/" className="text-sm text-[#7c6cff] hover:text-[#a99bff] transition-colors">← VerifAI</a>
        <h1 className="display text-3xl sm:text-4xl font-extrabold gradient-text mt-6 mb-2">Accuracy &amp; Methodology</h1>
        <p className="text-xs text-faint mb-10">
          We publish how the numbers are measured, not just the numbers. The model retrains nightly and
          promotes to production only through a strict quality gate. Last updated: July 2026.
        </p>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">Current model performance</h2>
          <p className="text-sm text-muted leading-relaxed mb-4">
            Measured by stratified 5-fold cross-validation on 1,005 labeled videos
            (400 AI-generated / 605 real), out-of-fold predictions only — the model is
            never scored on a video it trained on. Probabilities are isotonic-calibrated.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat value="0.982" label="ROC AUC" />
            <Stat value="97.7%" label="Precision" note="flagged AI → really AI" />
            <Stat value="85.3%" label="Recall" note="AI videos caught" />
            <Stat value="1.3%" label="False-positive rate" note="real flagged as AI" />
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">Measured on real-world footage</h2>
          <p className="text-sm text-muted leading-relaxed mb-4">
            An automated benchmark runs the full production pipeline on real videos the model has
            never seen — pulled from the Internet Archive and Wikimedia Commons, including the hard
            cases that fool detectors (chaotic motion like flour/confetti/water splashes, CCTV and
            dashcam footage, aerial/drone). It measures how often <b className="text-gray-200">real
            footage is wrongly flagged as AI</b>. The set grows on every run.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat value="123+" label="Real videos tested" note="Archive.org + Wikimedia" />
            <Stat value="1.3%" label="False-positive rate" note="on blind real footage" />
            <Stat value="98.7%" label="Specificity" note="real kept real" />
          </div>
          <p className="text-xs text-faint mt-3">
            Real user-supplied media is folded in permanently as ground-truth &quot;real&quot; signal, so the
            model keeps learning not to false-positive on everyday photos and phone footage.
          </p>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-white mb-3">What these numbers do and don&apos;t claim</h2>
          <ul className="text-sm text-muted leading-relaxed space-y-2 list-disc pl-5">
            <li>
              They measure the <b className="text-gray-200">statistical signature model</b> — one layer of the stack.
              Hard evidence (a validly signed C2PA credential, a platform&apos;s own AI label, an
              AI tool&apos;s metadata signature) decides directly at 93–99% confidence and doesn&apos;t
              depend on this model at all.
            </li>
            <li>
              Cross-validation is honest but shares a collection distribution with training.
              A <b className="text-gray-200">blind real-world benchmark</b> (collected across platforms,
              including deliberately hard cases like chaotic real footage and human CGI) runs
              continuously; results are published here as the set grows.
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
          <ol className="text-sm text-muted leading-relaxed space-y-2 list-decimal pl-5">
            <li><b className="text-gray-200">File forensics</b> — cryptographic C2PA verification, AI-tool metadata, proprietary MP4 boxes, codec fingerprints.</li>
            <li><b className="text-gray-200">Platform intelligence</b> — TikTok AIGC, YouTube &quot;Altered or synthetic content&quot;, Meta &quot;AI info&quot; labels, read where they survive transcoding.</li>
            <li><b className="text-gray-200">Vision ensemble</b> — Gemini temporal-pair analysis fused in log-odds space with frame, frequency, motion and audio models.</li>
          </ol>
          <p className="text-xs text-faint mt-3">
            Every API response includes an <code className="text-[#7c6cff]">explanation</code> object showing which
            layer decided and every layer&apos;s score — audit it yourself.
          </p>
        </section>

        <div className="flex gap-4 text-sm">
          <a href="/#detect" className="text-[#7c6cff] hover:text-[#a99bff] transition-colors">Try it →</a>
          <a href="/privacy" className="text-muted hover:text-white transition-colors">Privacy</a>
        </div>
      </div>
    </div>
  );
}
