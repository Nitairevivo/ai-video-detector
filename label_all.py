"""
Labels all videos in AI_Videos and Real_Videos, then trains the model.
Run:
  python label_all.py           # fast mode (metadata only)
  python label_all.py --deep    # include visual+frequency analysis (slower, better)
  python label_all.py --reset   # clear existing training data and start fresh
"""
import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import extract_features
from models.classifier import get_classifier

parser = argparse.ArgumentParser()
parser.add_argument("--deep", action="store_true", help="Run visual+frequency analysis per video (~10s each)")
parser.add_argument("--reset", action="store_true", help="Clear existing training data before labeling")
parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip files already in training set")
args = parser.parse_args()

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
import os as _os
from pathlib import Path as _Path

# Dataset root: VERIFAI_DATASET_DIR env, else the original dev path, else ./dataset_cache
_default = _Path("/Users/nitai/Desktop/dataset")
_ROOT = _Path(_os.environ.get("VERIFAI_DATASET_DIR", "").strip() or
              (_default if _default.exists() else _Path(__file__).parent / "dataset_cache"))

AI_DIR   = _ROOT / "AI_Videos"
REAL_DIR = _ROOT / "Real_Videos"
TRAINING_DATA_PATH = Path(__file__).parent / "data" / "training_samples.json"

# Optionally reset
if args.reset and TRAINING_DATA_PATH.exists():
    TRAINING_DATA_PATH.unlink()
    print("Training data cleared.")

# Load existing sources to skip duplicates
existing_sources: set[str] = set()
if args.skip_existing and TRAINING_DATA_PATH.exists():
    with open(TRAINING_DATA_PATH) as f:
        existing = json.load(f)
    existing_sources = {s.get("source", "") for s in existing}
    print(f"Skipping {len(existing_sources)} already-labeled files.")

classifier = get_classifier()
ai_count = real_count = skipped = errors = 0


def label_dir(folder: Path, is_ai: bool):
    global ai_count, real_count, skipped, errors
    label_str = "AI  " if is_ai else "Real"

    if not folder.exists():
        print(f"  Folder not found: {folder}. Skipping.")
        return

    files = sorted([f for f in folder.iterdir() if f.suffix.lower() in EXTENSIONS])
    print(f"\n{'='*60}")
    print(f"Labeling {len(files)} files as {label_str} from {folder.name}")
    if args.deep:
        print("  (deep mode: visual + frequency analysis enabled)")
    print('='*60)

    for i, f in enumerate(files, 1):
        if f.name in existing_sources:
            skipped += 1
            continue

        try:
            result = extract_features(str(f), deep=args.deep)

            # Sanity check: if this is supposedly AI but has strong camera markers, warn
            if is_ai and result.confidence < 0.15 and result.method.startswith("Camera"):
                print(f"  ! WARN | {f.name[:60]}")
                print(f"         Strong camera markers — may be a false AI label. Skipping.")
                errors += 1
                continue

            classifier.add_sample(result.feature_vector, label=is_ai, source=f.name)

            if is_ai:
                ai_count += 1
            else:
                real_count += 1

            # Show detection summary per file
            tool_info = f" [{result.ai_tool}]" if result.ai_tool else ""
            conf_str = f"{result.confidence*100:.0f}%"
            print(f"  [{i:3d}/{len(files)}] {label_str} | {conf_str:>4} | {f.name[:55]}{tool_info}")

        except Exception as e:
            errors += 1
            print(f"  [{i:3d}/{len(files)}] ERROR | {f.name[:55]} → {e}")


label_dir(AI_DIR,   is_ai=True)
label_dir(REAL_DIR, is_ai=False)

print(f"\n{'='*60}")
print(f"Labeled:  {ai_count} AI + {real_count} Real")
print(f"Skipped:  {skipped} (already in dataset)")
print(f"Errors:   {errors}")

# Count total in dataset
total_ai = total_real = 0
if TRAINING_DATA_PATH.exists():
    with open(TRAINING_DATA_PATH) as f:
        all_samples = json.load(f)
    total_ai   = sum(1 for s in all_samples if s["label"] == 1)
    total_real = sum(1 for s in all_samples if s["label"] == 0)
    print(f"Dataset:  {total_ai} AI + {total_real} Real total")

# Train if we have enough
MIN_EACH = 10
if total_ai >= MIN_EACH and total_real >= MIN_EACH:
    print(f"\nTraining ML model on {total_ai + total_real} samples...")
    train_result = classifier.train()
    if "error" in train_result:
        print(f"  ERROR: {train_result['error']}")
    else:
        print(f"  Trained on {train_result['samples_used']} samples "
              f"({train_result['ai_samples']} AI, {train_result['real_samples']} Real)")
        print(f"  Cross-val AUC: {train_result['cv_auc_mean']:.3f} "
              f"± {train_result['cv_auc_std']:.3f}")
        print(f"  Model saved → {train_result['model_saved']}")
else:
    missing_ai   = max(0, MIN_EACH - total_ai)
    missing_real = max(0, MIN_EACH - total_real)
    print(f"\nNot enough samples to train yet.")
    if missing_ai:
        print(f"  Need {missing_ai} more AI videos in {AI_DIR}")
    if missing_real:
        print(f"  Need {missing_real} more Real videos in {REAL_DIR}")
    print(f"  Run: python download_dataset.py --quick")
