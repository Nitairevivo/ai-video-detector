"""
Grow the REAL class from key-free sources that work on CI runners
(archive.org + Wikimedia Commons). Proven reachable from GitHub Actions — no
API key, no residential IP needed. Downloads a batch, extracts the code-first
feature vector from each clip, appends it to the training set as REAL, then
discards the video (only feature vectors are stored).

Usage:  python training/collect_freesources.py --per-query 6
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from train_forever import label_file, retrain, _trained_sources
from models.classifier import get_classifier


def collect(per_query: int, retrain_every: int = 100) -> int:
    from tests.collect_cloud_benchmark import collect_archive_org, collect_wikimedia
    from train_forever import real_class_saturated, dataset_stats

    # Don't worsen a starved AI class — more real footage past the cap is noise.
    if real_class_saturated():
        ai, real = dataset_stats()
        print(f"[freesrc] skipped — real class saturated ({real} real vs {ai} AI). "
              f"Waiting for diverse AI instead of piling on real.")
        return 0

    classifier = get_classifier()
    seen = _trained_sources()
    added = 0
    tmp = Path(tempfile.mkdtemp(prefix="freesrc_"))
    try:
        rows = []
        for fn in (collect_archive_org, collect_wikimedia):
            try:
                rows += fn(tmp, per_query)
            except Exception as e:
                print(f"[freesrc] {fn.__name__}: {e}")
        print(f"[freesrc] downloaded {len(rows)} real clips")
        for row in rows:
            path = tmp / row["filename"]
            tag = f"freesrc:{row['filename']}"
            # dedup must match the sanitized name actually stored as the source
            # below — comparing the raw tag never matched, re-collecting clips.
            stored = tag.replace("/", "_").replace(":", "_")
            if not path.exists() or stored in seen or tag in seen:
                continue
            renamed = path.with_name(stored)
            try:
                os.replace(path, renamed)
                path = renamed
            except Exception:
                pass
            if label_file(path, is_ai=False, classifier=classifier):
                added += 1
                if added % retrain_every == 0:
                    retrain(classifier)
            try:
                os.unlink(path)
            except Exception:
                pass
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    if added:
        retrain(classifier)
    print(f"[freesrc] added {added} real samples")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=6)
    args = ap.parse_args()
    print(f"done: +{collect(args.per_query)}")


if __name__ == "__main__":
    main()
