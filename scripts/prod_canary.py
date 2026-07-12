#!/usr/bin/env python3
"""
Production canary: exercises every detection path against the LIVE server and
fails loudly when one regresses. Runs weekly from GitHub Actions (and on
demand) — a failing run emails the repo owner, which is how we notice silent
breakage like a platform changing its AI-label format or a bad deploy
(both have happened) before users do.

Stdlib only — no dependencies to install on the runner.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

API = os.environ.get("VERIFAI_API", "https://ai-video-detector-production-a305.up.railway.app")

# Known-ground-truth URLs. If one of these disappears from YouTube the canary
# will fail — replace it with another one whose truth is just as certain.
SORA_LABELED_URL = "https://www.youtube.com/watch?v=-Nb-M1GAOX8"   # official Sora music video, YT AI-label
REAL_UNLABELED_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" (2005)

FAILURES = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def post_json(path: str, body: dict, timeout: int = 150):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def post_files(path: str, files: list, timeout: int = 240):
    """files: list of (fieldname, filename, bytes, mime)."""
    boundary = uuid.uuid4().hex
    body = b""
    for field, fname, data, mime in files:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="{field}"; filename="{fname}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        API + path, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tests", "assets")


def make_test_video() -> bytes:
    """Committed synthetic clip — GitHub runners don't ship ffmpeg."""
    with open(os.path.join(ASSETS, "canary.mp4"), "rb") as f:
        return f.read()


def make_test_jpeg() -> bytes:
    with open(os.path.join(ASSETS, "canary.jpg"), "rb") as f:
        return f.read()


def main():
    # 1. Health
    try:
        with urllib.request.urlopen(API + "/", timeout=20) as r:
            health = json.loads(r.read().decode())
        check("health", health.get("status") == "ok" and health.get("model_trained") is True,
              json.dumps(health)[:120])
    except Exception as e:
        check("health", False, str(e))
        # Server down — everything else would just add noise.
        sys.exit(1)

    # 2. Platform AI label still detected (format changes silently — this is
    #    the check that catches it).
    st, body = post_json("/detect-url", {"url": SORA_LABELED_URL})
    check("sora-label detected",
          st == 200 and body.get("verdict") == "ai_generated"
          and body.get("confidence", 0) >= 0.9
          and "Platform AI" in str(body.get("detection_method", "")),
          f"http={st} verdict={body.get('verdict')} method={str(body.get('detection_method'))[:60]}")

    # 3. Real unlabeled video must yield an HONEST error or a real verdict —
    #    never a fabricated AI verdict (the HTML-as-video regression) and
    #    never a 500.
    st, body = post_json("/detect-url", {"url": REAL_UNLABELED_URL})
    check("real-video not misflagged",
          (st == 400) or (st == 200 and body.get("verdict") in ("real", "unknown")),
          f"http={st} verdict={body.get('verdict')} detail={str(body.get('detail'))[:60]}")

    # 4. /detect upload path alive (schema check, verdict value is not asserted
    #    for a synthetic clip).
    try:
        vid = make_test_video()
        st, body = post_files("/detect", [("file", "canary.mp4", vid, "video/mp4")])
        check("/detect alive", st == 200 and "verdict" in body and "confidence" in body,
              f"http={st} verdict={body.get('verdict')}")
    except Exception as e:
        check("/detect alive", False, str(e))

    # 5. Frame endpoints alive.
    try:
        jpg = make_test_jpeg()
        st, body = post_files("/detect-frame", [("file", "f.jpg", jpg, "image/jpeg")])
        check("/detect-frame alive", st == 200 and "verdict" in body,
              f"http={st} verdict={body.get('verdict')}")
        st, body = post_files("/detect-frames",
                              [("files", f"f{i}.jpg", jpg, "image/jpeg") for i in range(3)])
        check("/detect-frames alive", st == 200 and "verdict" in body,
              f"http={st} verdict={body.get('verdict')}")
    except Exception as e:
        check("frame endpoints alive", False, str(e))

    if FAILURES:
        print(f"\n{len(FAILURES)} canary check(s) FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nAll canary checks passed.")


if __name__ == "__main__":
    main()
