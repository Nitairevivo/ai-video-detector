// VerifAI Lab — invariants on the REAL source.
//
// Each check asserts that a specific past bug CANNOT silently come back. These
// run against the actual files (not a model), so if someone edits the real code
// and breaks the guarantee, the lab fails before an APK is ever sent.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

let failed = 0;
function check(name, cond) {
  if (!cond) failed++;
  console.log(`${cond ? "  ✓" : "  ✗"} ${name}`);
}
// count occurrences of a substring
const count = (s, sub) => s.split(sub).length - 1;

// ── OverlayService.java: the WhatsApp/Telegram screen-record bug class ──
const svc = read("mobile/plugins/OverlayService.java");
check("onLocalFileUnavailable() exists", /private void onLocalFileUnavailable\(\)/.test(svc));
check("…prompts for access before screen-recording",
  /onLocalFileUnavailable\(\)\s*\{[\s\S]*?hasAllFilesAccess\(\)[\s\S]*?promptAllFilesAccess[\s\S]*?startScreenCaptureFallback/.test(svc));
check("BOTH local-file dead-ends route through onLocalFileUnavailable() (>=2 calls)",
  count(svc, "onLocalFileUnavailable()") >= 2);
check("free daily gate exists (allowFreeCheckOrPrompt)", /boolean allowFreeCheckOrPrompt\(\)/.test(svc));
check("a cancelled tap refunds the free check", /finishDetection\(\);\s*\n\s*refundFreeCheck\(\)/.test(svc));
check("promptAllFilesAccess opens the All-Files-Access screen",
  /ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION/.test(svc));

// ── billing.ts: the paid-but-not-unlocked bug class ──
const billing = read("mobile/billing.ts");
check("syncEntitlement falls back to email-keyed /entitlement", /\/entitlement/.test(billing) && /K_EMAIL/.test(billing));
check("ensureAccount drops a stale key when switching emails", /deleteItemAsync\(K_APIKEY\)/.test(billing));
check("Pro flag is pushed to the native button", /setProStatus/.test(billing));

// ── App.tsx: the native paywall must actually open the upgrade screen ──
const app = read("mobile/App.tsx");
check("verifai://paywall opens the PremiumModal", /paywall[\s\S]{0,40}setShowPremium\(true\)/.test(app));

// ── Onboarding.tsx: the quiz-vanishes-on-first-run bug class ──
const onb = read("mobile/Onboarding.tsx");
check("Welcome CTA waits for the quiz to resolve", /disabled=\{!quizLoaded\}/.test(onb));
check("quiz load has a built-in fallback set", /DEFAULT_QUIZ/.test(onb) && /fb\.some/.test(onb));
check("quiz load is time-bounded", /Date\.now\(\) > (deadline|fbDeadline)/.test(onb));
check("All-Files-Access card is shown in onboarding", /requestAllFilesAccess/.test(onb));

// ── Manifest: the file-read permission must be declared ──
const appJson = read("mobile/app.json");
const plugin = read("mobile/plugins/withAndroidOverlay.js");
check("MANAGE_EXTERNAL_STORAGE is declared (app.json + plugin)",
  /MANAGE_EXTERNAL_STORAGE/.test(appJson) && /MANAGE_EXTERNAL_STORAGE/.test(plugin));

// ── server.py: billing endpoints ──
const server = read("api/server.py");
check("/entitlement endpoint exists", /@app\.post\("\/entitlement"/.test(server));
check("/upgrade guarantees a key row before checkout (no pay-but-free)",
  /def upgrade\([\s\S]*?get_key_by_email\(body\.email\)[\s\S]*?create_key\(body\.email/.test(server));

// ── free build must NOT be a Play build (else it always screen-records) ──
const eas = read("mobile/eas.json");
check("free GitHub build does not force PLAY_BUILD",
  !/apk-free[\s\S]*EXPO_PUBLIC_PLAY_BUILD/.test(read(".github/workflows/apk-free.yml")));

if (failed) { console.error(`\nINVARIANTS: ${failed} check(s) FAILED`); process.exit(1); }
console.log("INVARIANTS: all source guarantees hold");
