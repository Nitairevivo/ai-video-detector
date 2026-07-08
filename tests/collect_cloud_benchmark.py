"""
Cloud benchmark collector — assembles a labeled video set on a GitHub runner
(where the network isn't blocked), so the real-world benchmark can run without
anyone hand-collecting videos.

Sources & label confidence:
  • REAL  — Pexels stock footage. Genuine camera video, reliable label.
  • AI    — yt-dlp searches scoped to official AI-tool accounts / tool names.
            Best-effort label: these accounts overwhelmingly post AI output,
            but it's not cryptographically guaranteed like the real side.
            The benchmark report states this caveat explicitly.

Writes <out>/videos/*.mp4 and <out>/manifest.csv for tests/real_benchmark.py.

Env: PEXELS_API_KEY (required for the real side).
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Real footage — Pexels search terms, incl. the hard cases that fool detectors
PEXELS_QUERIES = [
    ("nature", "nature"), ("people talking", "people"), ("city street", "street"),
    ("cooking food", "people"), ("ocean waves", "nature"), ("sports running", "sports"),
    ("flour baking", "chaotic"), ("confetti celebration", "chaotic"),
    ("water splash slow motion", "chaotic"), ("dashcam driving", "cctv"),
    ("drone aerial", "aerial"), ("interview person", "people"),
]

# AI footage — yt-dlp searches scoped to official AI-generation tools
AI_QUERIES = [
    ("sora openai generated video", "sora"),
    ("kling ai generated video", "kling"),
    ("runway gen3 ai video", "runway"),
    ("pika ai generated video", "pika"),
    ("hailuo minimax ai video", "hailuo"),
    ("luma dream machine ai video", "luma"),
    ("veo google ai generated video", "veo"),
    ("ai generated video realistic person", "ai_person"),
]


def collect_pexels(out_dir: Path, per_query: int, api_key: str) -> list:
    rows = []
    for query, category in PEXELS_QUERIES:
        try:
            params = urllib.parse.urlencode({"query": query, "per_page": per_query, "size": "small"})
            req = urllib.request.Request(
                f"https://api.pexels.com/videos/search?{params}",
                headers={"Authorization": api_key},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  [pexels] {query}: {e}")
            continue

        for video in data.get("videos", []):
            vid = str(video["id"])
            files = sorted(video.get("video_files", []), key=lambda f: f.get("width") or 9999)
            mp4 = next((f for f in files if f.get("file_type") == "video/mp4"), None)
            if not mp4:
                continue
            fname = f"pexels_{vid}.mp4"
            dest = out_dir / fname
            if dest.exists():
                continue
            try:
                urllib.request.urlretrieve(mp4["link"], dest)
                if dest.stat().st_size > 10000:
                    rows.append({"filename": fname, "label": "real",
                                 "platform": "pexels", "category": category})
                    print(f"  [real] {fname} ({category})")
            except Exception as e:
                print(f"  [pexels] download {vid}: {e}")
    return rows


def collect_ai(out_dir: Path, per_query: int) -> list:
    rows = []
    for query, category in AI_QUERIES:
        tmpl = str(out_dir / "ai_%(id)s.%(ext)s")
        cmd = [
            "yt-dlp", f"ytsearch{per_query}:{query}",
            "--no-playlist", "--max-filesize", "40M",
            "--match-filter", "duration < 300",
            "--download-sections", "*0-30",
            "--format", "mp4/best[ext=mp4][height<=720]/best[height<=720]",
            "--merge-output-format", "mp4",
            "--ignore-errors", "--no-warnings", "--quiet",
            "-o", tmpl,
        ]
        before = {p.name for p in out_dir.glob("ai_*.mp4")}
        try:
            subprocess.run(cmd, timeout=180, capture_output=True)
        except subprocess.TimeoutExpired:
            pass
        for p in out_dir.glob("ai_*.mp4"):
            if p.name in before or p.stat().st_size < 10000:
                continue
            rows.append({"filename": p.name, "label": "ai",
                         "platform": "youtube", "category": category})
            print(f"  [ai]   {p.name} ({category})")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="benchmark_data")
    ap.add_argument("--per-query", type=int, default=3)
    args = ap.parse_args()

    out = Path(args.out)
    vids = out / "videos"
    vids.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    rows = []

    print("Collecting REAL footage from Pexels…")
    if api_key:
        rows += collect_pexels(vids, args.per_query, api_key)
    else:
        print("  PEXELS_API_KEY not set — skipping real side")

    print("Collecting AI footage via yt-dlp…")
    rows += collect_ai(vids, args.per_query)

    manifest = out / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "label", "platform", "category"])
        w.writeheader()
        w.writerows(rows)

    n_ai = sum(1 for r in rows if r["label"] == "ai")
    n_real = sum(1 for r in rows if r["label"] == "real")
    print(f"\nCollected {len(rows)} videos: {n_ai} AI / {n_real} real")
    print(f"Manifest: {manifest}")
    if n_ai == 0 or n_real == 0:
        print("WARNING: one class is empty — benchmark needs both.")


if __name__ == "__main__":
    main()
