// VerifAI Lab — runnable model of the native floating-button decision logic.
//
// This mirrors OverlayService.onButtonTapped() / allowFreeCheckOrPrompt() /
// onLocalFileUnavailable() so we can assert the RIGHT outcome for every
// scenario WITHOUT an Android device. It is a design guard: invariants.mjs
// separately checks the real Java still matches this shape.
//
// Outcomes: "cancel" | "paywall" | "read_file" | "detect_url" |
//           "prompt_access" | "screen"

function decide(s) {
  // s: { detectionPending, pro, dailyCount, dailyLimit, playBuild,
  //      accessibilityOn, app, allFilesAccess, fileSavedToPublicFolder,
  //      hasClipboardLink }
  const state = { ...s };

  // Second tap while working = cancel (and refund the free check).
  if (state.detectionPending) return { outcome: "cancel", dailyCount: Math.max(0, state.dailyCount) };

  // Freemium gate.
  if (!state.pro) {
    if (state.dailyCount >= state.dailyLimit) return { outcome: "paywall", dailyCount: state.dailyCount };
    state.dailyCount += 1; // a genuine check is consumed
  }

  if (state.playBuild) return { outcome: "screen", dailyCount: state.dailyCount };

  const fg = state.accessibilityOn ? state.app : null;
  const isLocalApp = fg === "whatsapp" || fg === "telegram";
  const fileReadable = state.allFilesAccess && state.fileSavedToPublicFolder;

  const onLocalFileUnavailable = () =>
    !state.allFilesAccess ? "prompt_access" : "screen";

  if (isLocalApp) {
    return { outcome: fileReadable ? "read_file" : onLocalFileUnavailable(), dailyCount: state.dailyCount };
  }

  // Link path (also the accessibility-OFF path for WhatsApp/Telegram).
  if (state.hasClipboardLink) return { outcome: "detect_url", dailyCount: state.dailyCount };
  // No link → recent local file? → else onLocalFileUnavailable (NOT silent screen).
  const recentReadable = state.allFilesAccess && state.fileSavedToPublicFolder &&
    (state.app === "whatsapp" || state.app === "telegram");
  if (recentReadable) return { outcome: "read_file", dailyCount: state.dailyCount };
  return { outcome: onLocalFileUnavailable(), dailyCount: state.dailyCount };
}

const base = {
  detectionPending: false, pro: false, dailyCount: 0, dailyLimit: 3,
  playBuild: false, accessibilityOn: true, app: "whatsapp",
  allFilesAccess: true, fileSavedToPublicFolder: true, hasClipboardLink: false,
};

const cases = [
  // The exact bug the user hit: accessibility OFF, no file access → must PROMPT, never screen.
  ["WhatsApp, a11y OFF, no access → prompt (not screen)",
    { ...base, accessibilityOn: false, allFilesAccess: false, fileSavedToPublicFolder: false }, "prompt_access"],
  ["WhatsApp, a11y ON, no access → prompt (not screen)",
    { ...base, allFilesAccess: false, fileSavedToPublicFolder: false }, "prompt_access"],
  ["Telegram, a11y OFF, no access → prompt (not screen)",
    { ...base, app: "telegram", accessibilityOn: false, allFilesAccess: false, fileSavedToPublicFolder: false }, "prompt_access"],
  // Happy path: access granted + WhatsApp saved file → read the real file.
  ["WhatsApp, access + saved file → read_file",
    { ...base }, "read_file"],
  ["WhatsApp, a11y OFF, access + saved file → read_file (link path recovers)",
    { ...base, accessibilityOn: false }, "read_file"],
  // Honest Android limit: Telegram private cache (not saved) + access → screen.
  ["Telegram, access but NOT saved (private cache) → screen",
    { ...base, app: "telegram", fileSavedToPublicFolder: false }, "screen"],
  // Freemium.
  ["Free user, 4th tap → paywall",
    { ...base, dailyCount: 3 }, "paywall"],
  ["Pro user, many taps → never paywall (reads file)",
    { ...base, pro: true, dailyCount: 999 }, "read_file"],
  // Cancel refunds.
  ["Second tap while working → cancel",
    { ...base, detectionPending: true }, "cancel"],
  // A real link in the clipboard on a non-local app → detect_url.
  ["YouTube link in clipboard → detect_url",
    { ...base, app: "youtube", accessibilityOn: false, hasClipboardLink: true,
      allFilesAccess: false, fileSavedToPublicFolder: false }, "detect_url"],
];

let failed = 0;
for (const [name, st, expected] of cases) {
  const { outcome } = decide(st);
  const ok = outcome === expected;
  if (!ok) failed++;
  console.log(`${ok ? "  ✓" : "  ✗"} ${name}  →  ${outcome}${ok ? "" : `  (expected ${expected})`}`);
}

// Freemium counting: 3 free checks then paywall, and a cancel refunds one.
{
  let s = { ...base, dailyCount: 0 };
  const seq = [];
  for (let i = 0; i < 4; i++) { const r = decide(s); s = { ...s, dailyCount: r.dailyCount }; seq.push(r.outcome); }
  const expected = ["read_file", "read_file", "read_file", "paywall"];
  const ok = JSON.stringify(seq) === JSON.stringify(expected);
  if (!ok) failed++;
  console.log(`${ok ? "  ✓" : "  ✗"} Freemium: 3 free then paywall  →  ${seq.join(",")}`);
}

if (failed) { console.error(`\nLOGIC: ${failed} case(s) FAILED`); process.exit(1); }
console.log("LOGIC: all native-decision cases passed");
