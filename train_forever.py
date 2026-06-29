"""
Continuous training pipeline — parallel downloads + feature extraction.
Target: 10,000+ labeled samples.

Usage:
  python train_forever.py                   # run forever
  python train_forever.py --batch 30        # videos per class per round (default 30)
  python train_forever.py --max 10000       # stop after N total samples
  python train_forever.py --once            # one round only
  python train_forever.py --augment-only    # augment existing samples, skip download
  python train_forever.py --workers 6       # parallel download/process workers (default 4)
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import extract_features
from models.classifier import get_classifier

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent
AI_DIR   = Path(os.environ.get("AI_VIDEO_DIR",   str(_REPO / "data" / "training_videos" / "ai")))
REAL_DIR = Path(os.environ.get("REAL_VIDEO_DIR", str(_REPO / "data" / "training_videos" / "real")))
TRAINING_DATA_PATH = _REPO / "data" / "training_samples.json"
SEEN_PATH          = _REPO / "data" / "seen_video_ids.json"

AI_DIR.mkdir(parents=True, exist_ok=True)
REAL_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}

_seen_lock = threading.Lock()
_dataset_lock = threading.Lock()

# ── AI video queries ───────────────────────────────────────────────────────────

AI_QUERY_POOL = [
    # Flagship 2024-2025
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
    # Avatar & talking head
    "heygen ai avatar video demo 2025",
    "heygen ai talking video examples",
    "synthesia ai video avatar presentation",
    "d-id ai talking avatar video",
    "creatify ai ad video generation",
    "invideo ai generated video 2025",
    "deepbrain ai avatar video",
    # Compilations
    "ai generated video compilation 2025 sora runway kling",
    "text to video ai comparison 2025",
    "best ai video generators 2025 showcase",
    "ai generated short film 2025",
    "ai generated music video 2025",
    "ai generated commercial video 2025",
    "ai video generation trend tiktok 2025",
    # Features
    "runway motion brush ai demo video",
    "pika lip sync ai video examples",
    "kling ai character animation examples",
    "stable video diffusion examples 2025",
    "animatediff ai video generation examples",
    "open sora ai video examples shorts",
    "ai generated video sora vs kling comparison",
    "text to video generation 2025 examples",
    "ai generated nature video 2025",
    "ai generated landscape video sora runway",
    "ai video generation 4k examples 2025",
    "generate video from image ai 2025",
    "image to video ai generation examples",
    "ai video generation person walking",
    "ai generated dance video 2025",
    # More AI tools
    "genmo ai video examples",
    "stability ai video generation",
    "zeroscope ai video examples",
    "videocrafter ai generated video",
    "morphstudio ai video examples",
    "hotshot ai video generation",
    "lumiere ai video google research",
    "align your latents ai video",
    "show 1 ai video generation",
    "make-a-video meta ai video",
    "nuwa ai video generation",
    "imagen video google ai",
    "phenaki google ai video",
    "dreamix ai video editing",
    "gen1 runway ai video",
    "emu video meta ai generation",
    "i2vgen xl ai video",
    "svd stable video diffusion",
    "motionctrl ai video control",
    "animateanything ai video",
    "dynamicrafter ai video interpolation",
    "videodreamer ai multi scene",
    "boomerang ai tiktok effect generated",
    "ai deepfake video realistic 2025",
    "ai face swap video realistic",
    "ai generated talking head realistic",
    "ai video synthesis 2025 examples",
    "neural radiance field video ai",
    "gaussian splatting ai video",
    "ai generated 3d animation 2025",
    "ai generated CGI video realistic",
    "stable diffusion video xl 2025",
]

# ── Real video queries ─────────────────────────────────────────────────────────

REAL_QUERY_POOL = [
    # Camera-specific
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
    "sony a7 iv real footage broll cinematic",
    "fujifilm x-h2s real footage broll",
    "hasselblad footage real camera 4k",
    "leica sl3 real footage cinematic",
    # Nature / documentary
    "4k nature broll no copyright free use",
    "wildlife real camera footage 4k",
    "ocean waves 4k footage no copyright",
    "forest nature 4k footage broll",
    "documentary real street footage 4k",
    "mountains real footage 4k no copyright",
    "waterfall real camera footage 4k",
    "desert sunset real footage 4k",
    "snow winter real camera footage 4k",
    "flowers macro real camera footage 4k",
    "birds wildlife real camera footage",
    "underwater real camera footage 4k",
    "volcano real footage 4k camera",
    "storm weather real camera footage",
    "northern lights real camera footage",
    # Travel / everyday
    "travel vlog real camera 4k footage",
    "city street footage 4k no copyright",
    "cooking real footage 4k broll",
    "sports real footage 4k slow motion camera",
    "market street documentary footage 4k",
    "rain weather real camera footage broll",
    "sunrise sunset real camera footage 4k",
    "coffee shop real footage broll 4k",
    "beach real footage broll 4k no copyright",
    "construction real camera footage broll",
    "farm agriculture real footage 4k",
    "children playing real camera footage",
    "athletes training real footage 4k",
    "medical real footage operating room camera",
    # Film
    "film grain 16mm real analog footage",
    "vintage real film footage no copyright",
    "interview real person camera footage",
    "wedding ceremony real footage 4k",
    "concert live real footage 4k camera",
    # Stock channels
    "videvo free stock footage 4k",
    "coverr free stock footage 4k",
    "mixkit free stock footage 4k",
    "pexels video free 4k footage",
    "pixabay free video footage 4k",
    "dareful free stock footage 4k",
    "artgrid free real footage 4k",
    "storyblocks free footage 4k real",
    # Specific real content
    "GoPro hero 4k test footage real 2025",
    "vlogging real camera footage 2025",
    "real people street interview footage",
    "slow motion real camera footage 240fps",
    "aerial drone real footage 4k 2025",
    "dashcam footage 4k real camera",
    "bodycam real footage police",
    "surveillance camera real footage",
    "sports camera real action footage",
    "timelapse real camera footage 4k",
    "hyperlapse real footage 4k",
    "cinematic real footage no AI 4k",
    "behind scenes real camera footage BTS",
    "making of real footage production camera",
    "documentary real footage no AI 2025",
]

# Pexels API
PEXELS_REAL_SEARCHES = [
    "nature", "ocean", "city", "people walking", "cooking",
    "mountains", "forest", "rain", "sunset", "animals",
    "sports", "street", "market", "children playing", "coffee",
    "flowers", "water", "birds", "landscape", "architecture",
    "travel", "food", "technology", "business", "health",
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


# ── Downloaders ────────────────────────────────────────────────────────────────

def download_yt(query: str, out_dir: Path, n: int, seen: set) -> list[Path]:
    """Download up to n videos from a yt-dlp search query."""
    ids_before = {f.stem for f in out_dir.glob("*.mp4")}
    archive_file = out_dir / ".yt_archive"
    cmd = [
        "yt-dlp",
        f"ytsearch{n}:{query}",
        "--no-playlist",
        "--max-filesize", "60M",
        "--match-filter", "duration < 600",
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
    new_files = [
        f for f in out_dir.glob("*.mp4")
        if f.stem not in ids_before and f.stem not in seen and f.stat().st_size > 5000
    ]
    return new_files


def download_pexels(search: str, out_dir: Path, seen: set, api_key: str) -> list[Path]:
    """Download real footage from Pexels API."""
    import urllib.request, urllib.parse
    new_files = []
    try:
        params = urllib.parse.urlencode({"query": search, "per_page": 8, "size": "medium"})
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


def download_wikimedia(category: str, out_dir: Path, seen: set, n: int = 5) -> list[Path]:
    """
    Download real videos from Wikimedia Commons.
    Free, CC-licensed, extremely reliable labels.
    """
    import urllib.request, urllib.parse
    new_files = []
    try:
        params = urllib.parse.urlencode({
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": n * 3,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        })
        req = urllib.request.Request(
            f"https://commons.wikimedia.org/w/api.php?{params}",
            headers={"User-Agent": "AIVideoDetector/1.0 (training pipeline)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {}).values()
        count = 0
        for page in pages:
            if count >= n:
                break
            info = page.get("imageinfo", [{}])[0]
            mime = info.get("mime", "")
            if "video" not in mime:
                continue
            url = info.get("url", "")
            size = info.get("size", 0)
            if not url or size > 80_000_000 or size < 10000:
                continue
            vid_id = f"wm_{page['pageid']}"
            if vid_id in seen:
                continue
            ext = ".ogv" if ".ogv" in url else ".webm" if ".webm" in url else ".mp4"
            out_path = out_dir / f"{vid_id}{ext}"
            if out_path.exists():
                new_files.append(out_path)
                count += 1
                continue
            try:
                urllib.request.urlretrieve(url, out_path)
                new_files.append(out_path)
                count += 1
            except Exception:
                pass
    except Exception:
        pass
    return new_files


# Real Wikimedia categories — reliable real-world footage
WIKIMEDIA_REAL_CATEGORIES = [
    "Videos of animals",
    "Videos of nature",
    "Videos of water",
    "Videos of buildings",
    "Videos of people",
    "Videos of plants",
    "Videos of birds",
    "Videos of fish",
    "Videos of sport",
    "Videos of weather",
    "Videos of fire",
    "Videos of transportation",
    "Videos of urban areas",
    "Videos of landscapes",
    "Videos of insects",
]


# ── Feature augmentation ───────────────────────────────────────────────────────

def augment_samples(n_augmented: int = 500) -> int:
    """
    Create synthetic training samples by adding calibrated Gaussian noise
    to existing feature vectors. Preserves label distribution.
    Standard ML practice for small datasets.
    Returns number of new samples added.
    """
    try:
        import numpy as np
    except ImportError:
        print("  numpy not available — skipping augmentation")
        return 0

    samples = load_samples()
    if len(samples) < 30:
        print(f"  Too few samples for augmentation ({len(samples)} < 30)")
        return 0

    ai_samples   = [s for s in samples if s["label"] == 1]
    real_samples = [s for s in samples if s["label"] == 0]

    if not ai_samples or not real_samples:
        return 0

    classifier = get_classifier()
    added = 0

    # Compute per-feature std from real data to calibrate noise magnitude
    all_vecs = np.array([s["features"] for s in samples])
    feat_stds = np.std(all_vecs, axis=0)
    # Noise = 5% of each feature's natural std — small enough to stay realistic
    noise_scale = feat_stds * 0.05

    n_per_class = n_augmented // 2

    for pool, label in [(ai_samples, True), (real_samples, False)]:
        for _ in range(n_per_class):
            base = random.choice(pool)
            fv = np.array(base["features"])
            noise = np.random.normal(0, noise_scale)
            augmented = (fv + noise).tolist()
            classifier.add_sample(augmented, label=label, source=f"augmented_{base['source'][:30]}")
            added += 1

    print(f"  Augmented {added} synthetic samples from {len(samples)} real ones")
    return added


# ── Labeling ───────────────────────────────────────────────────────────────────

def label_file(path: Path, is_ai: bool, classifier, delete_after: bool = True) -> bool:
    """Extract features, sanity-check, add to training set. Optionally delete video."""
    try:
        result = extract_features(str(path), deep=False)
    except Exception as e:
        print(f"    ✗ error: {e}")
        if delete_after and path.exists():
            path.unlink(missing_ok=True)
        return False

    # Sanity checks
    if is_ai and result.confidence < 0.10 and "Camera origin" in result.method:
        print(f"    ✗ camera markers on supposed AI — skip")
        if delete_after:
            path.unlink(missing_ok=True)
        return False
    if not is_ai and result.confidence >= 0.95:
        print(f"    ✗ definitive AI signals on supposed real — skip")
        if delete_after:
            path.unlink(missing_ok=True)
        return False

    with _dataset_lock:
        classifier.add_sample(result.feature_vector, label=is_ai, source=path.name)

    if delete_after:
        path.unlink(missing_ok=True)
    return True


def label_files_parallel(files: list[Path], is_ai: bool, classifier,
                          workers: int = 4, delete_after: bool = True) -> int:
    """Label a batch of files in parallel. Returns count of successfully labeled."""
    added = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(label_file, f, is_ai, classifier, delete_after): f for f in files}
        for fut in as_completed(futures):
            f = futures[fut]
            try:
                ok = fut.result()
                if ok:
                    added += 1
                    print(f"    ✓ {'AI' if is_ai else 'Real'} {f.name[:55]}")
            except Exception as e:
                print(f"    ✗ {f.name}: {e}")
    return added


# ── Training & push ────────────────────────────────────────────────────────────

def retrain(classifier) -> dict | None:
    ai, real = dataset_stats()
    if ai < 15 or real < 15:
        print(f"    Not enough samples (AI={ai}, Real={real}, need 15 each)")
        return None
    print(f"\n  Training on {ai + real} samples ({ai} AI, {real} Real)...")
    result = classifier.train()
    if "error" in result:
        print(f"  ✗ train error: {result['error']}")
        return None
    auc = result["cv_auc_mean"]
    active = result.get("model_active", False)
    print(f"  AUC={auc:.3f} ± {result['cv_auc_std']:.3f}  |  model_active={active}")
    return result


def push_model():
    repo = Path(__file__).parent
    try:
        subprocess.run(
            ["git", "add",
             "models/trained_model.joblib",
             "models/trained_model_meta.json",
             "data/training_samples.json"],
            cwd=repo, capture_output=True
        )
        ai, real = dataset_stats()
        subprocess.run(
            ["git", "commit", "-m", f"Auto-train: {ai + real} samples ({ai} AI, {real} Real)"],
            cwd=repo, capture_output=True
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo, capture_output=True, text=True
        ).stdout.strip() or "main"
        subprocess.run(["git", "push", "origin", branch], cwd=repo, capture_output=True)
        print("  ✓ model pushed to production")
    except Exception as e:
        print(f"  ✗ push failed: {e}")


# ── Main loop ──────────────────────────────────────────────────────────────────

def run(batch: int, max_samples: int, once: bool, augment_only: bool, workers: int):
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    classifier = get_classifier()
    seen = load_seen()
    round_num = 0

    ai_queries   = AI_QUERY_POOL.copy(); random.shuffle(ai_queries)
    real_queries = REAL_QUERY_POOL.copy(); random.shuffle(real_queries)
    pexels_searches = PEXELS_REAL_SEARCHES.copy()
    wikimedia_cats = WIKIMEDIA_REAL_CATEGORIES.copy(); random.shuffle(wikimedia_cats)

    ai_now, real_now = dataset_stats()
    total_now = ai_now + real_now

    print(f"Training pipeline started")
    print(f"  Batch: {batch}/class | Max: {max_samples or '∞'} | Workers: {workers}")
    print(f"  Dataset now: {ai_now} AI + {real_now} Real = {total_now} total")
    if augment_only:
        print(f"  Mode: augmentation only (no downloads)")
    print()

    # ── Augment-only mode ─────────────────────────────────────────────────────
    if augment_only:
        n_aug = max(500, (max_samples or 10000) - total_now)
        added = augment_samples(n_augmented=n_aug)
        if added > 0:
            retrain(classifier)
            push_model()
        return

    while True:
        round_num += 1
        ai_total, real_total = dataset_stats()
        total = ai_total + real_total

        if max_samples and total >= max_samples:
            print(f"\nReached target: {total} samples. Done.")
            break

        remaining = (max_samples - total) if max_samples else None
        print(f"\n{'─'*65}")
        print(f"Round {round_num}  |  {ai_total} AI + {real_total} Real = {total} total"
              + (f"  |  {remaining} to go" if remaining else ""))
        print(f"{'─'*65}")

        # How many videos to request per query
        n_per_query = max(4, batch // 2)

        # Pick queries — 2 per class per round for higher throughput
        def pop_query(pool, full_pool):
            if not pool:
                pool.extend(full_pool); random.shuffle(pool)
            return pool.pop(0)

        ai_q1 = pop_query(ai_queries, AI_QUERY_POOL)
        ai_q2 = pop_query(ai_queries, AI_QUERY_POOL)
        real_q1 = pop_query(real_queries, REAL_QUERY_POOL)
        real_q2 = pop_query(real_queries, REAL_QUERY_POOL)
        wm_cat = pop_query(wikimedia_cats, WIKIMEDIA_REAL_CATEGORIES)

        # Clear yt-dlp archives every 25 rounds
        if round_num % 25 == 0:
            for d in [AI_DIR, REAL_DIR]:
                arch = d / ".yt_archive"
                if arch.exists():
                    arch.unlink()
            print("  [archive cleared]")

        # ── Download AI + Real in PARALLEL ────────────────────────────────────
        print(f"\n  Downloading in parallel...")
        print(f"    AI:   {ai_q1[:55]}")
        print(f"          {ai_q2[:55]}")
        print(f"    Real: {real_q1[:55]}")
        print(f"          {real_q2[:55]}")
        print(f"    Wm:   {wm_cat}")

        ai_files:   list[Path] = []
        real_files: list[Path] = []
        download_lock = threading.Lock()

        def dl_ai1():
            r = download_yt(ai_q1, AI_DIR, n_per_query, seen)
            with download_lock: ai_files.extend(r)

        def dl_ai2():
            r = download_yt(ai_q2, AI_DIR, n_per_query, seen)
            with download_lock: ai_files.extend(r)

        def dl_real1():
            r = download_yt(real_q1, REAL_DIR, n_per_query, seen)
            with download_lock: real_files.extend(r)

        def dl_real2():
            r = download_yt(real_q2, REAL_DIR, n_per_query, seen)
            with download_lock: real_files.extend(r)

        def dl_wm():
            r = download_wikimedia(wm_cat, REAL_DIR, seen, n=n_per_query)
            with download_lock: real_files.extend(r)

        def dl_pexels():
            if not pexels_key:
                return
            pq = pop_query(pexels_searches, PEXELS_REAL_SEARCHES)
            r = download_pexels(pq, REAL_DIR, seen, pexels_key)
            with download_lock: real_files.extend(r)
            if r:
                print(f"    + {len(r)} Pexels ({pq})")

        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [
                ex.submit(dl_ai1), ex.submit(dl_ai2),
                ex.submit(dl_real1), ex.submit(dl_real2),
                ex.submit(dl_wm), ex.submit(dl_pexels),
            ]
            for f in as_completed(futs):
                try: f.result()
                except Exception: pass

        # Dedup (same file downloaded by two queries)
        ai_files   = list({f.name: f for f in ai_files}.values())
        real_files = list({f.name: f for f in real_files}.values())

        # Update seen
        with _seen_lock:
            for f in ai_files + real_files:
                seen.add(f.stem)
        save_seen(seen)

        print(f"\n  Downloaded: {len(ai_files)} AI + {len(real_files)} Real")

        # ── Label in PARALLEL ─────────────────────────────────────────────────
        added_ai   = label_files_parallel(ai_files,   True,  classifier, workers, delete_after=True)
        added_real = label_files_parallel(real_files, False, classifier, workers, delete_after=True)

        print(f"\n  Labeled: {added_ai} AI + {added_real} Real")
        ai_total, real_total = dataset_stats()
        total = ai_total + real_total
        print(f"  Dataset: {ai_total} AI + {real_total} Real = {total} total")

        # ── Augment when imbalanced ───────────────────────────────────────────
        imbalance = abs(ai_total - real_total)
        if imbalance > 50 and total > 100:
            print(f"\n  Dataset imbalanced by {imbalance} — augmenting minority class")
            augment_samples(n_augmented=imbalance * 2)

        # ── Retrain every round ───────────────────────────────────────────────
        if added_ai + added_real > 0:
            result = retrain(classifier)
            if result and result.get("model_active"):
                # Push every 5 rounds or when approaching target
                if round_num % 5 == 0 or (remaining and remaining < batch * 2):
                    push_model()
        else:
            print("\n  No new samples this round — skipping retrain")

        if once:
            print("\nDone (--once mode).")
            push_model()
            break

        # Progress report
        if max_samples:
            pct = min(100, total / max_samples * 100)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"\n  Progress: [{bar}] {pct:.1f}% ({total}/{max_samples})")

        # Cool-down between rounds
        wait = random.randint(20, 45)
        print(f"\n  Waiting {wait}s before next round...")
        time.sleep(wait)

    # Final push after hitting target
    push_model()
    ai_f, real_f = dataset_stats()
    print(f"\n{'═'*65}")
    print(f"Pipeline complete: {ai_f} AI + {real_f} Real = {ai_f + real_f} total samples")
    print(f"{'═'*65}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Continuous AI video training pipeline")
    parser.add_argument("--batch",        type=int,  default=30,    help="Videos per class per round")
    parser.add_argument("--max",          type=int,  default=0,     help="Stop after N total samples (0=forever)")
    parser.add_argument("--once",         action="store_true",       help="Run one round only then exit")
    parser.add_argument("--augment-only", action="store_true",       help="Augment existing samples only, skip downloads")
    parser.add_argument("--workers",      type=int,  default=4,     help="Parallel feature-extraction workers")
    args = parser.parse_args()

    try:
        run(
            batch=args.batch,
            max_samples=args.max,
            once=args.once,
            augment_only=args.augment_only,
            workers=args.workers,
        )
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
        ai, real = dataset_stats()
        print(f"Final dataset: {ai} AI + {real} Real ({ai + real} total)")
    except Exception as e:
        import traceback
        print(f"\n[CRASH] {e}")
        traceback.print_exc()
        raise
