export const metadata = { title: "Privacy Policy — VerifAI" };

const sections: Array<{ title: string; body: string[] }> = [
  {
    title: "What we process",
    body: [
      "When you submit a video (file or URL), VerifAI analyzes it to determine whether it was AI-generated. Analysis reads the file's technical metadata (encoder tags, C2PA Content Credentials, container structure), samples a small number of frames, and computes statistical signals.",
      "For URL submissions we fetch the video from the platform on your behalf and may read the platform's public page data (such as its own AI-disclosure labels).",
    ],
  },
  {
    title: "Videos are deleted immediately",
    body: [
      "Submitted videos are written to temporary storage for the duration of the analysis only and are deleted as soon as the analysis completes — including when it fails. We do not build a library of your videos.",
      "Frames sampled for AI-vision analysis are sent to the model provider (Google Gemini) for inference and are subject to the provider's API data-handling terms.",
    ],
  },
  {
    title: "What we keep",
    body: [
      "We keep the detection result metadata needed to operate the service: request logs (endpoint, timing, status), your API-key usage counters for billing, and — if you explicitly submit a labeled sample for training — the numeric feature vector of that video (not the video itself).",
      "Detection history shown in the web app is stored in your own browser (localStorage), not on our servers.",
    ],
  },
  {
    title: "Accounts & billing",
    body: [
      "API keys are tied to the email address you register. Payments are processed by Stripe; we never see or store card numbers.",
    ],
  },
  {
    title: "Contact",
    body: [
      "Questions or deletion requests: contact us through the dashboard and we will respond promptly.",
    ],
  },
];

export default function Privacy() {
  return (
    <div className="min-h-screen text-gray-300" style={{ background: "#0a0a13" }}>
      <div className="max-w-2xl mx-auto px-6 py-16">
        <a href="/" className="text-sm text-violet-400 hover:text-violet-300">← VerifAI</a>
        <h1 className="text-3xl font-extrabold text-white mt-6 mb-2">Privacy Policy</h1>
        <p className="text-xs text-gray-500 mb-10">Last updated: July 2026</p>
        {sections.map((s) => (
          <section key={s.title} className="mb-8">
            <h2 className="text-lg font-bold text-white mb-2">{s.title}</h2>
            {s.body.map((p, i) => (
              <p key={i} className="text-sm leading-relaxed text-gray-400 mb-2">{p}</p>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
