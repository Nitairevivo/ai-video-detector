"""
Continuous training pipeline — runs indefinitely.
Downloads AI + real videos, labels them, retrains the model every batch.

Usage:
  python train_forever.py                  # run forever
  python train_forever.py --batch 20       # 20 videos per round (default 30)
  python train_forever.py --max 500        # stop after 500 total samples
  python train_forever.py --once           # one round only
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import extract_features
from models.classifier import get_classifier

# ── Paths ─────────────────────────────────────────────────────────────────────
# Dataset location is configurable so the loop can run anywhere (cloud worker,
# CI, any machine) — not just on one laptop. Order of preference:
#   1. VERIFAI_DATASET_DIR env var
#   2. the original local dev path, if it exists on this machine
#   3. ./dataset_cache next to the repo
_default_root = Path("/Users/nitai/Desktop/dataset")
DATASET_ROOT = Path(
    os.environ.get("VERIFAI_DATASET_DIR", "").strip()
    or (_default_root if _default_root.exists() else Path(__file__).parent / "dataset_cache")
)
AI_DIR   = DATASET_ROOT / "AI_Videos"
REAL_DIR = DATASET_ROOT / "Real_Videos"
TRAINING_DATA_PATH = Path(__file__).parent / "data" / "training_samples.json"
SEEN_PATH          = Path(__file__).parent / "data" / "seen_video_ids.json"

AI_DIR.mkdir(parents=True, exist_ok=True)
REAL_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}

# ── Video sources ──────────────────────────────────────────────────────────────

# AI video queries — rotated each round for variety
AI_QUERY_POOL = [
    # Flagship tools 2024-2025
    "sora openai video generation 2025",
    "sora openai video examples shorts",
    "runway gen4 ai video examples 2025",
    "runway gen3 ai generated video",
    "runway gen4 image to video examples",
    "kling 1.6 ai video generation examples",
    "kling ai video generation 2025 shorts",
    "kling 2.0 ai video generation",
    "pika 2.1 ai video generation",
    "pika labs ai video shorts 2025",
    "hailuo minimax ai video 2025",
    "hailuo ai video generation examples",
    "luma dream machine ai video 2025",
    "luma ray2 ai video demo",
    "veo 2 google ai video generated",
    "veo 3 google ai generated video",
    "wan 2.0 ai video generation",
    "wan ai video generation examples 2025",
    "hunyuan video tencent ai generation",
    "cogvideo ai generated short 2025",
    "stepvideo ai generation examples",
    "seaweed bytedance ai video generation",
    "mochi genmo ai video examples",
    "haiper ai video generation 2025",
    # Avatar & talking head tools
    "heygen ai avatar video demo 2025",
    "heygen ai talking video examples",
    "synthesia ai video avatar presentation",
    "d-id ai talking avatar video",
    "creatify ai ad video generation",
    "invideo ai generated video 2025",
    "deepbrain ai avatar video",
    # Compilations & showcases
    "ai generated video compilation 2025 sora runway kling",
    "text to video ai comparison 2025",
    "best ai video generators 2025 showcase",
    "ai video generation showcase before after 2025",
    "ai generated short film 2025",
    "ai generated music video 2025",
    "ai generated commercial video 2025",
    "ai video generation trend tiktok 2025",
    # Tool-specific features
    "runway motion brush ai demo video",
    "pika lip sync ai video examples",
    "kling ai character animation examples",
    "stable video diffusion examples 2025",
    "animatediff ai video generation examples",
    "open sora ai video examples shorts",
    # More specific searches
    "ai generated video sora vs kling comparison",
    "text to video generation 2025 examples",
    "ai video generation timelapse 2025",
    "ai generated nature video 2025",
    "ai generated landscape video sora runway",
    "ai video generation 4k examples 2025",
    "generate video from image ai 2025",
    "image to video ai generation examples",
    "ai video generation person walking",
    "ai generated dance video 2025",
]

# Real video queries — strong camera metadata signals
REAL_QUERY_POOL = [
    # Camera-specific → strong EXIF/encoder metadata
    "sony fx3 footage broll 4k no copyright",
    "sony fx3 cinematic footage 2025",
    "gopro hero12 4k adventure footage",
    "gopro hero12 black footage broll",
    "iphone 15 pro max cinematic footage broll",
    "iphone 15 pro camera test footage",
    "dji mini 4 pro 4k drone footage",
    "dji air 3 drone footage 4k",
    "canon r5 cinematic broll footage",
    "canon r6 mark ii footage broll",
    "nikon z9 real footage outdoor broll",
    "nikon zf footage broll 4k",
    "red camera real footage cinema broll",
    "blackmagic pocket 6k footage broll 2025",
    "sigma fp real footage broll cinematic",
    "lumix s5 ii real footage broll",
    # Nature / documentary — guaranteed real
    "4k nature broll no copyright free use",
    "wildlife real camera footage 4k",
    "ocean waves 4k footage no copyright",
    "forest nature 4k footage broll",
    "documentary real street footage 4k",
    "mountains real footage 4k no copyright",
    "waterfall real camera footage 4k",
    "desert sunset real footage 4k",
    "snow winter real camera footage 4k",
    # Travel / everyday real life
    "travel vlog real camera 4k footage",
    "city street footage 4k no copyright",
    "cooking real footage 4k broll",
    "sports real footage 4k slow motion camera",
    "market street documentary footage 4k",
    "rain weather real camera footage broll",
    "sunrise sunset real camera footage 4k",
    "coffee shop real footage broll 4k",
    "beach real footage broll 4k no copyright",
    # Film & analog
    "film grain 16mm real analog footage",
    "vintage real film footage no copyright",
    "interview real person camera footage",
    "wedding ceremony real footage 4k",
    "concert live real footage 4k camera",
    # Stock footage channels (reliable real footage)
    "videvo free stock footage 4k",
    "coverr free stock footage 4k",
    "mixkit free stock footage 4k",
    "pexels video free 4k footage",
    "pixabay free video footage 4k",
    "dareful free stock footage 4k",
    # Specific real content
    "GoPro hero 4k test footage real 2025",
    "vlogging real camera footage 2025",
    "real people street interview footage",
    "slow motion real camera footage 240fps",
    "aerial drone real footage 4k 2025",
]

# Pexels API for real stock footage (free, no copyright, reliable labels)
PEXELS_REAL_SEARCHES = [
    "nature", "ocean", "city", "people walking", "cooking",
    "mountains", "forest", "rain", "sunset", "animals",
    "sports", "street", "market", "children playing", "coffee",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_PATH.write_text(json.dumps(list(seen)))


def load_samples() -> list:
    if TRAINING_DATA_PATH.exists():
        return json.loads(TRAINING_DATA_PATH.read_text())
    return []


def dataset_stats() -> tuple[int, int]:
    samples = load_samples()
    ai   = sum(1 for s in samples if s["label"] == 1)
    real = sum(1 for s in samples if s["label"] == 0)
    return ai, real


def download_yt(query: str, out_dir: Path, n: int, seen: set) -> list[Path]:
    """Download up to n videos from a yt-dlp search query. Returns new files."""
    ids_before = {f.stem for f in out_dir.glob("*.mp4")}
    # Only use archive if it exists (cleared periodically to allow new queries)
    archive_file = out_dir / ".yt_archive"

    cmd = [
        "yt-dlp",
        f"ytsearch{n}:{query}",
        "--no-playlist",
        "--max-filesize", "60M",
        # Accept videos up to 10 min — AI demos & comparison videos are often long
        "--match-filter", "duration < 600",
        # Only download first 40 seconds — enough for metadata + codec patterns
        "--download-sections", "*0-40",
        "--format", "mp4/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]",
        "--merge-output-format", "mp4",
        "--download-archive", str(archive_file),
        "--ignore-errors",
        "--quiet",
        "--embed-metadata",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    try:
        subprocess.run(cmd, timeout=180, capture_output=True)
    except subprocess.TimeoutExpired:
        pass

    # Return files whose stem (= video ID) is new
    new_files = [
        f for f in out_dir.glob("*.mp4")
        if f.stem not in ids_before and f.stem not in seen and f.stat().st_size > 5000
    ]
    return new_files


def download_pexels(search: str, out_dir: Path, seen: set, api_key: str) -> list[Path]:
    """Download real footage from Pexels API (free, reliable labels)."""
    import urllib.request, urllib.parse
    new_files = []
    try:
        params = urllib.parse.urlencode({"query": search, "per_page": 5, "size": "medium"})
        req = urllib.request.Request(
            f"https://api.pexels.com/videos/search?{params}",
            headers={"Authorization": api_key}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        for video in data.get("videos", []):
            vid_id = str(video["id"])
            if vid_id in seen:
                continue
            # Pick smallest SD file
            files = sorted(video.get("video_files", []), key=lambda f: f.get("width", 9999))
            mp4 = next((f for f in files if f.get("file_type") == "video/mp4"), None)
            if not mp4:
                continue
            out_path = out_dir / f"pexels_{vid_id}.mp4"
            if out_path.exists():
                continue
            urllib.request.urlretrieve(mp4["link"], out_path)
            new_files.append(out_path)
    except Exception:
        pass
    return new_files


def label_file(path: Path, is_ai: bool, classifier) -> bool:
    """Extract features, sanity-check, and add to training set. Returns True if added."""
    try:
        result = extract_features(str(path), deep=False)
    except Exception as e:
        print(f"    ✗ error: {e}")
        return False

    # Sanity checks — reject mislabeled samples
    if is_ai and result.confidence < 0.10 and "Camera origin" in result.method:
        print(f"    ✗ strong camera markers on supposed AI — skip")
        return False
    if not is_ai and result.confidence >= 0.95:
        print(f"    ✗ definitive AI signals on supposed real — skip")
        return False

    classifier.add_sample(result.feature_vector, label=is_ai, source=path.name)
    return True


def _trained_sources() -> set:
    """Filenames already present in the training set (authoritative dedup)."""
    try:
        return {s.get("source", "") for s in load_samples()}
    except Exception:
        return set()


def _harvest_existing(classifier, seen: set) -> int:
    """
    Label any video already on disk that isn't in the training set yet.
    This prevents downloaded-but-unlabeled files from being wasted — the bug
    that left the dataset frozen at 220 while 800+ files sat unused.
    """
    trained = _trained_sources()
    added = 0
    for d, is_ai in ((AI_DIR, True), (REAL_DIR, False)):
        if not d.exists():
            continue
        for f in d.glob("*"):
            if f.suffix.lower() not in EXTENSIONS or f.stat().st_size < 10000:
                continue
            if f.name in trained:
                seen.add(f.stem)
                continue
            if label_file(f, is_ai=is_ai, classifier=classifier):
                trained.add(f.name)
                seen.add(f.stem)
                added += 1
    return added


def retrain(classifier):
    ai, real = dataset_stats()
    if ai < 15 or real < 15:
        print(f"    Not enough samples to train yet (AI={ai}, Real={real}, need 15 each)")
        return None
    print(f"\n  Training on {ai + real} samples ({ai} AI, {real} Real)...")
    result = classifier.train()
    if "error" in result:
        print(f"  ✗ train error: {result['error']}")
        return None
    auc = result["cv_auc_mean"]
    active = result.get("model_active", False)
    print(f"  AUC={auc:.3f} ± {result['cv_auc_std']:.3f}  |  model active={active}")
    return result


def push_model():
    """Commit and push updated model to trigger production deploy."""
    repo = Path(__file__).parent
    try:
        subprocess.run(
            ["git", "add",
             "models/trained_model.joblib",
             "models/trained_model_meta.json",
             "data/training_samples.json"],
            cwd=repo, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m",
             f"Auto-train: {dataset_stats()[0]+dataset_stats()[1]} samples"],
            cwd=repo, capture_output=True
        )
        subprocess.run(["git", "push", "origin", "master"], cwd=repo, capture_output=True)
        print("  ✓ pushed to production")
    except Exception as e:
        print(f"  ✗ push failed: {e}")


# ── Main loop ──────────────────────────────────────────────────────────────────

def run(batch: int, max_samples: int, once: bool):
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    classifier = get_classifier()
    seen = load_seen()
    round_num = 0

    ai_queries   = AI_QUERY_POOL.copy()
    real_queries = REAL_QUERY_POOL.copy()
    pexels_searches = PEXELS_REAL_SEARCHES.copy()

    random.shuffle(ai_queries)
    random.shuffle(real_queries)

    print(f"Starting continuous training pipeline")
    print(f"  Batch size: {batch} per class | Max: {max_samples} | Once: {once}")

    # Harvest any already-downloaded files that were never labeled, so nothing
    # sitting on disk is wasted (this is what left the dataset stuck at 220).
    harvested = _harvest_existing(classifier, seen)
    if harvested:
        print(f"  Harvested {harvested} on-disk files into the training set")
        save_seen(seen)
        retrain(classifier)

    ai_now, real_now = dataset_stats()
    print(f"  Current dataset: {ai_now} AI + {real_now} Real\n")

    while True:
        round_num += 1
        ai_total, real_total = dataset_stats()
        if max_samples and (ai_total + real_total) >= max_samples:
            print(f"\nReached max samples ({max_samples}). Done.")
            break

        print(f"\n{'─'*60}")
        print(f"Round {round_num}  |  dataset: {ai_total} AI + {real_total} Real")
        print(f"{'─'*60}")

        # Pick queries for this round (rotate through pool)
        n_per_query = max(3, batch // 3)
        ai_q   = ai_queries.pop(0)   if ai_queries   else random.choice(AI_QUERY_POOL)
        real_q = real_queries.pop(0) if real_queries else random.choice(REAL_QUERY_POOL)
        if not ai_queries:
            ai_queries = AI_QUERY_POOL.copy()
            random.shuffle(ai_queries)
        if not real_queries:
            real_queries = REAL_QUERY_POOL.copy()
            random.shuffle(real_queries)

        # Clear yt-dlp archives every 8 rounds so queries keep finding new videos
        # (30 was too slow — the pipeline starved and added 0 samples for hours).
        if round_num % 8 == 0:
            for d in [AI_DIR, REAL_DIR]:
                arch = d / ".yt_archive"
                if arch.exists():
                    arch.unlink()
            print("  [archive cleared — queries refreshed]")

        # ── Download AI ───────────────────────────────────────────────────────
        print(f"\n  [AI] {ai_q}")
        ai_files = download_yt(ai_q, AI_DIR, n_per_query, seen)
        print(f"       {len(ai_files)} new files downloaded")

        added_ai = 0
        for f in ai_files:
            seen.add(f.stem)
            ok = label_file(f, is_ai=True, classifier=classifier)
            if ok:
                added_ai += 1
                print(f"    ✓ AI   {f.name[:55]}")
        print(f"       added {added_ai} AI samples")

        # ── Download Real ─────────────────────────────────────────────────────
        print(f"\n  [Real] {real_q}")
        real_files = download_yt(real_q, REAL_DIR, n_per_query, seen)
        print(f"         {len(real_files)} new files downloaded")

        # Supplement with Pexels if key available
        if pexels_key and len(real_files) < 3:
            pq = pexels_searches.pop(0) if pexels_searches else random.choice(PEXELS_REAL_SEARCHES)
            if not pexels_searches:
                pexels_searches = PEXELS_REAL_SEARCHES.copy()
            pexels_files = download_pexels(pq, REAL_DIR, seen, pexels_key)
            real_files += pexels_files
            if pexels_files:
                print(f"         + {len(pexels_files)} from Pexels ({pq})")

        added_real = 0
        for f in real_files:
            seen.add(f.stem)
            ok = label_file(f, is_ai=False, classifier=classifier)
            if ok:
                added_real += 1
                print(f"    ✓ Real {f.name[:55]}")
        print(f"         added {added_real} Real samples")

        save_seen(seen)

        # ── Retrain ───────────────────────────────────────────────────────────
        if added_ai + added_real > 0:
            result = retrain(classifier)
            if result and result.get("model_active"):
                push_model()
        else:
            print("\n  No new samples this round — skipping train")

        if once:
            print("\nDone (--once mode).")
            break

        # Cool-down between rounds to avoid rate limiting
        wait = random.randint(30, 60)
        print(f"\n  Waiting {wait}s before next round...")
        time.sleep(wait)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch",  type=int, default=30,   help="Videos per class per round")
    parser.add_argument("--max",    type=int, default=0,    help="Stop after N total samples (0=forever)")
    parser.add_argument("--once",   action="store_true",    help="Run one round only")
    args = parser.parse_args()

    try:
        run(batch=args.batch, max_samples=args.max, once=args.once)
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
        ai, real = dataset_stats()
        print(f"Final dataset: {ai} AI + {real} Real ({ai+real} total)")
    except Exception as e:
        # macOS notification on unexpected crash so launchd restart is visible
        import subprocess as _sp
        _sp.run([
            "osascript", "-e",
            f'display notification "train_forever crashed: {str(e)[:80]}" with title "AI Video Detector" subtitle "Training pipeline restarting…"'
        ], capture_output=True)
        raise
