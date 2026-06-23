"""
Downloads AI and Real videos from YouTube for training.
Run: python download_dataset.py
"""
import subprocess
import sys
from pathlib import Path

AI_DIR   = Path("/Users/nitai/Desktop/dataset/AI_Videos")
REAL_DIR = Path("/Users/nitai/Desktop/dataset/Real_Videos")
AI_DIR.mkdir(parents=True, exist_ok=True)
REAL_DIR.mkdir(parents=True, exist_ok=True)

# Search queries for AI-generated videos
AI_QUERIES = [
    "ytsearch20:sora openai video generation showcase 2025",
    "ytsearch20:runway gen3 ai video examples",
    "ytsearch20:kling ai video generation examples shorts",
    "ytsearch20:pika 2.0 ai video generation",
    "ytsearch15:hailuo minimax ai video shorts",
    "ytsearch15:luma dream machine ai video 2025",
    "ytsearch15:veo google ai video generated",
    "ytsearch15:deepfake ai face video realistic 2025",
    "ytsearch15:ai generated music video sora runway",
    "ytsearch15:cogvideo ai generated short film",
]

REAL_QUERIES = [
    "ytsearch20:4k nature broll no copyright real camera",
    "ytsearch20:sony fx3 fx30 cinematic real footage",
    "ytsearch20:gopro hero 4k real adventure footage",
    "ytsearch15:iphone 15 pro cinematic real video",
    "ytsearch15:drone dji 4k real nature footage",
    "ytsearch15:documentary real people street footage 4k",
    "ytsearch15:travel vlog real camera footage 4k",
    "ytsearch15:film grain 16mm real footage cinematic",
]

BASE_OPTS = [
    "yt-dlp",
    "--no-playlist",
    "--max-filesize", "200M",
    "--format", "mp4/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]",
    "--merge-output-format", "mp4",
    "--no-overwrites",
    "--ignore-errors",
    "--quiet",
    "--progress",
    "--no-warnings",
    "--write-info-json",
]

def download_batch(queries, out_dir, label):
    print(f"\n{'='*60}")
    print(f"Downloading {label} videos → {out_dir.name}")
    print('='*60)
    for query in queries:
        print(f"\n  🔍 {query[:70]}")
        cmd = BASE_OPTS + [
            "-o", str(out_dir / "%(title).60s [%(id)s].%(ext)s"),
            query,
        ]
        result = subprocess.run(cmd, capture_output=False)
        count = len(list(out_dir.glob("*.mp4")))
        print(f"  → Total in folder: {count} videos")

download_batch(AI_QUERIES,   AI_DIR,   "AI-generated")
download_batch(REAL_QUERIES, REAL_DIR, "Real footage")

ai_count   = len(list(AI_DIR.glob("*.mp4")))
real_count = len(list(REAL_DIR.glob("*.mp4")))
print(f"\n✓ Done: {ai_count} AI + {real_count} Real videos total")
print(f"\nNext: python label_all.py")
