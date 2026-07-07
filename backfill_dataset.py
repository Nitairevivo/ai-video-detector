"""
Backfill the training set from videos ALREADY downloaded to disk.

train_forever.py only labels files it downloads in the moment; hundreds of
already-downloaded clips in the dataset folders were never added. This walks
both folders, extracts features from every not-yet-seen file, applies the same
sanity checks, adds them to the training set, and retrains once at the end.

    python backfill_dataset.py                 # process everything
    python backfill_dataset.py --limit 200     # cap per class
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyzer import extract_features
from models.classifier import get_classifier

AI_DIR = Path("/Users/nitai/Desktop/dataset/AI_Videos")
REAL_DIR = Path("/Users/nitai/Desktop/dataset/Real_Videos")
TRAINING_DATA_PATH = Path(__file__).parent / "data" / "training_samples.json"
EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def existing_sources() -> set:
    if TRAINING_DATA_PATH.exists():
        try:
            return {s.get("source", "") for s in json.loads(TRAINING_DATA_PATH.read_text())}
        except Exception:
            return set()
    return set()


def sane(is_ai: bool, result) -> bool:
    """Reject obviously mislabeled samples (same rule train_forever uses)."""
    if is_ai and result.confidence < 0.10 and "Camera origin" in result.method:
        return False
    if not is_ai and result.confidence >= 0.95:
        return False
    return True


def process(d: Path, is_ai: bool, seen: set, classifier, limit: int) -> tuple:
    files = [f for f in d.glob("*") if f.suffix.lower() in EXTS and f.stat().st_size > 10000]
    added = skipped = rejected = 0
    for f in files:
        if limit and added >= limit:
            break
        if f.name in seen:
            skipped += 1
            continue
        try:
            result = extract_features(str(f), deep=False)
        except Exception as e:
            print(f"    ✗ {f.name[:40]}: {e}")
            rejected += 1
            continue
        if not sane(is_ai, result):
            rejected += 1
            continue
        classifier.add_sample(result.feature_vector, label=is_ai, source=f.name)
        seen.add(f.name)
        added += 1
        if added % 25 == 0:
            print(f"    …{added} added from {d.name}")
    return added, skipped, rejected


def main(limit: int):
    classifier = get_classifier()
    seen = existing_sources()
    t0 = time.time()

    print(f"Backfilling. Already in training set: {len(seen)} sources\n")

    a_add, a_skip, a_rej = process(AI_DIR, True, seen, classifier, limit)
    print(f"  AI:   +{a_add} added, {a_skip} already there, {a_rej} rejected")
    r_add, r_skip, r_rej = process(REAL_DIR, False, seen, classifier, limit)
    print(f"  Real: +{r_add} added, {r_skip} already there, {r_rej} rejected")

    total_new = a_add + r_add
    print(f"\n  {total_new} new samples in {time.time()-t0:.0f}s")

    if total_new:
        print("\n  Retraining…")
        res = classifier.train()
        if "error" in res:
            print(f"  ✗ {res['error']}")
        else:
            print(f"  Samples: {res['samples_used']} ({res['ai_samples']} AI, {res['real_samples']} Real)")
            print(f"  CV AUC : {res['cv_auc_mean']*100:.1f}% ± {res['cv_auc_std']*100:.1f}%")
            print(f"  Model active: {res['model_active']}  ({res['quality_gate']})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0, help="cap per class (0=all)")
    args = p.parse_args()
    main(args.limit)
