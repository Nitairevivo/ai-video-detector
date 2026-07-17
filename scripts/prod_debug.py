#!/usr/bin/env python3
"""
Production vision-layer diagnostic. Answers ONE question with evidence:
is the Gemini base layer actually running on live detections, or has it
silently died (quota / revoked key / model change) — which degrades every
verdict to heuristics-only and makes obvious AI videos read as "real"?

Prints the full /health payload and the full ensemble breakdown of a real
/detect call, so the answer is read off the response, not guessed.

Stdlib only — runs on a bare GitHub runner.
"""
import json
import os
import sys
import urllib.request
import uuid

API = os.environ.get("VERIFAI_API", "https://ai-video-detector-production-a305.up.railway.app")
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tests", "assets")


def get(path: str, timeout: int = 30):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_files(path: str, files: list, timeout: int = 240):
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


def main():
    print("=" * 70)
    print("1. /health")
    print("=" * 70)
    try:
        health = get("/health")
        print(json.dumps(health, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    print()
    print("=" * 70)
    print("2. /detect (canary.mp4) — full ensemble breakdown")
    print("=" * 70)
    with open(os.path.join(ASSETS, "canary.mp4"), "rb") as f:
        vid = f.read()
    st, body = post_files("/detect", [("file", "canary.mp4", vid, "video/mp4")])
    print(f"HTTP {st}")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:4000])
    layers = body.get("ensemble_layers") or {}
    print()
    print(f">>> GEMINI LAYER RAN: {'YES' if 'gemini' in layers else 'NO'}")
    print(f">>> layers: {layers}")

    print()
    print("=" * 70)
    print("3. /detect-frames (3x canary.jpg) — screen-burst path")
    print("=" * 70)
    with open(os.path.join(ASSETS, "canary.jpg"), "rb") as f:
        jpg = f.read()
    st, body = post_files("/detect-frames",
                          [("files", f"f{i}.jpg", jpg, "image/jpeg") for i in range(3)])
    print(f"HTTP {st}")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:2000])
    method = str(body.get("detection_method", ""))
    print()
    print(f">>> BURST USED GEMINI: {'YES' if 'Gemini' in method else 'NO'} (method: {method[:100]})")

    print()
    print("=" * 70)
    print("4. /health again — gemini call counters after the two detections")
    print("=" * 70)
    try:
        health2 = get("/health")
        print(json.dumps(health2.get("gemini", "no 'gemini' field (old server build)"),
                         indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"FAILED: {e}")


if __name__ == "__main__":
    main()
