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


def collect_wikimedia(out_dir: Path, per_query: int) -> list:
    """
    Real footage from Wikimedia Commons — freely licensed, NO API key, and not
    IP-blocked from datacenter runners. The no-key fallback for the real side.
    """
    rows = []
    api = "https://commons.wikimedia.org/w/api.php"
    searches = [
        ("nature landscape", "nature"), ("people walking city", "people"),
        ("ocean waves", "nature"), ("cooking", "people"),
        ("water splash", "chaotic"), ("traffic street", "street"),
        ("bird flying", "nature"), ("train railway", "aerial"),
    ]
    for term, category in searches:
        params = urllib.parse.urlencode({
            "action": "query", "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:video {term}",
            "gsrnamespace": "6", "gsrlimit": str(per_query),
            # videoinfo derivatives = pre-transcoded low-res versions; the
            # originals on Commons are often 100MB+ documentaries and get
            # rejected on size, which starved earlier runs down to ~2 files.
            "prop": "videoinfo", "viprop": "url|size|mediatype|derivatives",
        })
        try:
            req = urllib.request.Request(f"{api}?{params}",
                                         headers={"User-Agent": "VerifAI-Benchmark/1.0 (research)"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  [wikimedia] {term}: {e}")
            continue

        pages = (data.get("query", {}) or {}).get("pages", {}) or {}
        for page in pages.values():
            info = (page.get("videoinfo") or [{}])[0]
            if info.get("mediatype") != "VIDEO":
                continue
            # Pick the smallest usable derivative (prefer ~240-480p transcodes)
            candidates = []
            for d in info.get("derivatives", []) or []:
                src = d.get("src", "")
                if not src.startswith("http"):
                    continue
                height = int(d.get("height") or 0)
                if 120 <= height <= 640:
                    candidates.append((height, src))
            if not candidates and info.get("url") and (info.get("size") or 0) <= 40 * 1024 * 1024:
                candidates = [(0, info["url"])]
            if not candidates:
                print(f"  [wikimedia] skip (no small derivative): {page.get('title','?')[:50]}")
                continue
            candidates.sort()
            url = candidates[0][1]
            ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".webm"
            if ext not in (".webm", ".ogv", ".mp4", ".mov"):
                continue
            fname = f"wiki_{abs(hash(url)) % 10**8}{ext}"
            dest = out_dir / fname
            if dest.exists():
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "VerifAI-Benchmark/1.0 (research)"})
                with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
                    f.write(r.read(40 * 1024 * 1024))
                if dest.stat().st_size > 10000:
                    rows.append({"filename": fname, "label": "real",
                                 "platform": "wikimedia", "category": category})
                    print(f"  [real] {fname} ({category})")
                else:
                    dest.unlink(missing_ok=True)
            except Exception as e:
                print(f"  [wikimedia] download: {e}")
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

    print("Collecting REAL footage…")
    if api_key:
        rows += collect_pexels(vids, args.per_query, api_key)
    else:
        print("  PEXELS_API_KEY not set — using Wikimedia Commons (no key needed)")
    # Always add Wikimedia too — more real samples, and the sole source with no key
    rows += collect_wikimedia(vids, args.per_query)

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
