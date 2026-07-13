"""
Scale the training set from Hugging Face video datasets.

Why this exists: the AI class is the collection bottleneck. yt-dlp is blocked on
datacenter IPs (GitHub runners), so we cannot pull AI videos from TikTok/YouTube
in the cloud. Hugging Face, however, IS reachable from CI and hosts large
public datasets of *generated* videos (AI) and *real* footage. This collector
streams video files from a HF dataset repo, extracts the code-first feature
vector from each, and appends it to data/training_samples.json — then discards
the video. Only feature vectors are stored, so the dataset can grow to tens of
thousands of samples without needing terabytes of disk.

Usage:
    python training/collect_hf.py --repo <dataset_id> --label ai   --limit 500
    python training/collect_hf.py --repo <dataset_id> --label real --limit 500

Repos are passed in (not hard-coded) so the pipeline can be pointed at whatever
public datasets are currently accessible; unreachable repos are skipped with a
logged reason instead of failing the whole run.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from train_forever import label_file, retrain, _trained_sources  # reuse the vetted path
from models.classifier import get_classifier

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".3gp", ".ogv")


def _iter_repo_videos(repo_id: str, limit: int, seen: set):
    """Yield (filename, local_path) for up to `limit` unseen video files in a HF
    dataset repo, downloading each lazily. Skips files already in the training set."""
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    token = os.environ.get("HF_TOKEN") or None
    try:
        files = api.list_repo_files(repo_id, repo_type="dataset", token=token)
    except Exception as e:
        print(f"[hf] cannot list {repo_id}: {e}")
        return

    vids = [f for f in files if f.lower().endswith(VIDEO_EXTS)]
    print(f"[hf] {repo_id}: {len(vids)} video files, downloading up to {limit} new ones")

    got = 0
    for f in vids:
        if got >= limit:
            break
        tag = f"hf:{repo_id}:{os.path.basename(f)}"
        # collect() stores the source under the sanitized name below, so dedup
        # must compare against THAT form (comparing the raw tag never matched,
        # so every clip was re-downloaded and duplicated every run).
        stored = tag.replace("/", "_").replace(":", "_")
        if stored in seen or tag in seen:
            continue
        try:
            local = hf_hub_download(repo_id, f, repo_type="dataset", token=token)
        except Exception as e:
            print(f"    ✗ download {f}: {e}")
            continue
        yield tag, Path(local)
        got += 1


def _record_hard_stats(repo_id: str, is_ai: bool, added: int, hard: int):
    """Append this repo's hard-sample rate to data/hard_samples_report.json so we
    can SEE which generators the model is weakest on and steer future collection
    toward them. A 'hard' sample is one the current model gets wrong at 0.5 — for
    the AI class these are exactly the misses that keep recall down."""
    import json
    from pathlib import Path
    p = Path(__file__).parent.parent / "data" / "hard_samples_report.json"
    try:
        rep = json.loads(p.read_text()) if p.exists() else {"repos": {}}
    except Exception:
        rep = {"repos": {}}
    rate = round(hard / added, 3) if added else 0.0
    rep["repos"][repo_id] = {
        "class": "ai" if is_ai else "real",
        "added": added, "hard": hard, "hard_rate": rate,
    }
    try:
        p.write_text(json.dumps(rep, indent=2))
    except Exception:
        pass


def collect(repo_id: str, is_ai: bool, limit: int, retrain_every: int = 200) -> int:
    classifier = get_classifier()
    seen = _trained_sources()
    added = 0
    hard = 0  # samples the CURRENT model gets wrong — the ones worth having
    for tag, path in _iter_repo_videos(repo_id, limit, seen):
        # label_file records source by filename; make it the unique HF tag so
        # dedup across runs works and we never re-count the same clip.
        try:
            renamed = path.with_name(tag.replace("/", "_").replace(":", "_"))
            os.replace(path, renamed)
            path = renamed
        except Exception:
            pass
        result = label_file(path, is_ai=is_ai, classifier=classifier)
        if result:
            added += 1
            # Hard-sample mining: does the current model already get this right?
            # The ones it misses are the ones that actually move recall/precision.
            try:
                prob, _ = classifier.predict(result.feature_vector)
                miss = (prob < 0.5) if is_ai else (prob >= 0.5)
                if miss:
                    hard += 1
            except Exception:
                pass
            if added % 25 == 0:
                print(f"[hf] {repo_id}: +{added} samples ({hard} hard so far)")
            if added % retrain_every == 0:
                retrain(classifier)
        try:
            os.unlink(path)   # keep only the feature vector, drop the video
        except Exception:
            pass
    if added:
        retrain(classifier)
        _record_hard_stats(repo_id, is_ai, added, hard)
    pct = (100 * hard / added) if added else 0
    print(f"[hf] {repo_id}: added {added} {'AI' if is_ai else 'real'} samples "
          f"— {hard} were HARD ({pct:.0f}% the model missed before training)")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Hugging Face dataset repo id")
    ap.add_argument("--label", required=True, choices=["ai", "real"])
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()
    n = collect(args.repo, is_ai=(args.label == "ai"), limit=args.limit)
    print(f"done: +{n}")


if __name__ == "__main__":
    main()
