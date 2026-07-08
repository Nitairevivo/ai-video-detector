"""
Downloads AI and Real videos from YouTube for training.
Run: python download_dataset.py
     python download_dataset.py --quick   # only 50 videos, fast
     python download_dataset.py --target 300  # aim for 300 per class
"""

# Script, not a module — top-level code downloads/labels/trains on import.
# Importing it by accident once retrained the model; fail fast instead.
if __name__ != "__main__":
    raise ImportError(__file__ + " is a command-line script; run it with python, do not import it")


import subprocess
import sys
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--quick", action="store_true", help="Download ~50 per class (fast)")
parser.add_argument("--target", type=int, default=150, help="Target videos per class")
args = parser.parse_args()

import os as _os
from pathlib import Path as _Path

# Dataset root: VERIFAI_DATASET_DIR env, else the original dev path, else ./dataset_cache
_default = _Path("/Users/nitai/Desktop/dataset")
_ROOT = _Path(_os.environ.get("VERIFAI_DATASET_DIR", "").strip() or
              (_default if _default.exists() else _Path(__file__).parent / "dataset_cache"))

AI_DIR   = _ROOT / "AI_Videos"
REAL_DIR = _ROOT / "Real_Videos"
AI_DIR.mkdir(parents=True, exist_ok=True)
REAL_DIR.mkdir(parents=True, exist_ok=True)

N = 10 if args.quick else 20

# AI-generated video queries — ordered by signal reliability
# (tools that leave strong metadata signatures come first)
AI_QUERIES = [
    # Tools with known container/metadata signatures — best training samples
    f"ytsearch{N}:sora openai video generation 2025 showcase",
    f"ytsearch{N}:runway gen4 ai video examples 2025",
    f"ytsearch{N}:kling 1.6 ai video generation examples",
    f"ytsearch{N}:pika 2.1 ai video generation shorts",
    f"ytsearch{N}:hailuo minimax ai video generation 2025",
    f"ytsearch{N}:luma dream machine ai video 2025",
    f"ytsearch{N}:veo 2 google ai video generated",
    f"ytsearch{N}:wan 2.0 ai video generation",
    f"ytsearch{N}:cogvideo ai generated short",
    f"ytsearch{N}:hunyuan video tencent ai generation",
    # Compilations of known AI tools
    f"ytsearch{N}:ai generated video compilation 2025 sora runway",
    f"ytsearch{N}:text to video ai generation comparison 2025",
    # Avatar / deepfake tools
    f"ytsearch{N}:heygen ai avatar video generation 2025",
    f"ytsearch{N}:synthesia ai video avatar demo",
]

REAL_QUERIES = [
    # Camera-specific queries → strong camera metadata signatures
    f"ytsearch{N}:sony fx3 footage broll 4k no copyright",
    f"ytsearch{N}:gopro hero12 4k real adventure footage",
    f"ytsearch{N}:iphone 15 pro max cinematic footage broll",
    f"ytsearch{N}:dji mini 4 pro 4k drone footage",
    f"ytsearch{N}:canon r5 r6 real cinematic broll",
    f"ytsearch{N}:4k nature broll no copyright free use",
    f"ytsearch{N}:documentary real people street footage 4k",
    f"ytsearch{N}:travel vlog real camera 4k footage",
    f"ytsearch{N}:film grain 16mm real analog footage cinematic",
    f"ytsearch{N}:nikon z9 real footage outdoor broll",
    f"ytsearch{N}:red camera real footage cinema broll",
    f"ytsearch{N}:wildlife real camera footage 4k bbc",
]

BASE_OPTS = [
    "yt-dlp",
    "--no-playlist",
    "--max-filesize", "100M",
    # Prefer shorter clips — better for training (less padding)
    "--match-filter", "duration < 120",
    "--format", "mp4/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]",
    "--merge-output-format", "mp4",
    "--no-overwrites",
    "--ignore-errors",
    "--quiet",
    "--progress",
    "--no-warnings",
    "--write-info-json",
    # Embed metadata in the file — preserves tool/encoder tags
    "--embed-metadata",
]


def download_batch(queries, out_dir, label, target):
    print(f"\n{'='*60}")
    print(f"Downloading {label} videos → {out_dir.name}  (target: {target})")
    print('='*60)
    for query in queries:
        current = len(list(out_dir.glob("*.mp4")))
        if current >= target:
            print(f"  Target reached ({current} videos). Stopping.")
            break
        print(f"\n  Searching: {query[:70]}")
        cmd = BASE_OPTS + [
            "-o", str(out_dir / "%(title).60s [%(id)s].%(ext)s"),
            query,
        ]
        subprocess.run(cmd, capture_output=False)
        print(f"  Total in folder: {len(list(out_dir.glob('*.mp4')))} videos")


target = 50 if args.quick else args.target
download_batch(AI_QUERIES,   AI_DIR,   "AI-generated", target)
download_batch(REAL_QUERIES, REAL_DIR, "Real footage",  target)

ai_count   = len(list(AI_DIR.glob("*.mp4")))
real_count = len(list(REAL_DIR.glob("*.mp4")))
print(f"\nDone: {ai_count} AI + {real_count} Real videos")
print(f"\nNext step: python label_all.py")
