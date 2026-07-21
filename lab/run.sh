#!/usr/bin/env bash
# VerifAI Lab — run BEFORE every APK build/send.
# Catches the bug classes we've actually shipped: the WhatsApp/Telegram
# screen-record gap, paid-but-not-unlocked, the vanishing onboarding quiz,
# compile/type errors, and server billing regressions.
#
# HONEST SCOPE: this does not boot a full Android emulator, so it can't verify
# real hardware behaviour (does listFiles() truly return null, does the overlay
# actually draw). It verifies all the LOGIC + that the real source still upholds
# every fix. Anything it can't cover is called out explicitly at the end.
set -uo pipefail
cd "$(dirname "$0")/.."
FAIL=0
step () { echo ""; echo "▶ $1"; }
run  () { if "$@"; then :; else echo "  ✗ FAILED: $*"; FAIL=1; fi; }

step "1/6  TypeScript typecheck (mobile)"
run bash -c "cd mobile && npx --no-install tsc --noEmit --skipLibCheck 2>&1 | (grep -E 'error TS' && exit 1 || exit 0)"

step "2/6  Native Java balances + plugin JS parses"
run python3 - <<'PY'
import sys
ok=True
for f in ["mobile/plugins/OverlayService.java","mobile/plugins/OverlayModule.java","mobile/plugins/VerifAIAccessibilityService.java"]:
    s=open(f).read()
    if s.count("{")!=s.count("}") or s.count("(")!=s.count(")"):
        print("  ✗ unbalanced",f); ok=False
print("  ✓ java balanced" if ok else "  ✗ java unbalanced")
sys.exit(0 if ok else 1)
PY
run node -c mobile/plugins/withAndroidOverlay.js

step "3/7  REAL native policy — compiled + run with javac (no emulator)"
run bash -c 'rm -rf lab/.jout && mkdir -p lab/.jout && javac -d lab/.jout mobile/plugins/DetectionPolicy.java lab/java/DetectionPolicyTest.java 2>&1 | grep -v "Picked up JAVA_TOOL_OPTIONS" ; java -Dfile.encoding=UTF-8 -cp lab/.jout com.verifai.app.DetectionPolicyTest 2>/dev/null'

step "4/7  Native decision-flow model (whole-tap state machine)"
run node lab/logic.mjs

step "5/7  Source invariants (fixes cannot silently regress)"
run node lab/invariants.mjs

step "6/7  Server billing / entitlement (database layer)"
run python3 -m pytest tests/test_entitlement_billing.py tests/test_database.py -q

step "7/7  Engine READS a real file's code → verdict (+ existing suite)"
run python3 -m pytest tests/test_engine_reads_file.py tests/test_bugfixes.py -q

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "✅ LAB PASSED — logic + source guarantees OK."
  echo "   NOT covered (needs a real device): overlay draw, real listFiles() on"
  echo "   Android/media, the permission dialog actually appearing, MediaProjection."
else
  echo "❌ LAB FAILED — do NOT send a build until green."
fi
exit $FAIL
