"""
Autonomous IMAGE data machine — the still-image counterpart of the video
grower. AI *images* are abundant and freely downloadable on Hugging Face
(unlike AI video, which is the bottleneck), so this side can actually scale.

For each image it extracts analyzer.image_analyzer.image_feature_vector (metadata
flags + pixel statistics), appends it to data/image_training_samples.json, and
retrains models/image_model.joblib — which analyze_image uses for the hard case
of a *stripped* image (screenshot / re-saved) that carries no provenance. Only
feature vectors are stored; the images are discarded.

Usage:
  python training/collect_images.py --ai-repos <id,id> --real-repos <id,id> --limit 500
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.image_analyzer import image_feature_vector, _IMG_FEATURE_KEYS

DATA = Path(__file__).parent.parent / "data" / "image_training_samples.json"
MODEL = Path(__file__).parent.parent / "models" / "image_model.joblib"
META = Path(__file__).parent.parent / "models" / "image_model_meta.json"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _load() -> list:
    if DATA.exists():
        try:
            return json.load(open(DATA))
        except Exception:
            return []
    return []


def _seen() -> set:
    return {s.get("source", "") for s in _load()}


def add_sample(vec, is_ai, source):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    samples = _load()
    samples.append({"features": vec, "label": int(is_ai), "source": source})
    json.dump(samples, open(DATA, "w"))


def collect_hf(repo: str, is_ai: bool, limit: int, seen: set) -> int:
    from huggingface_hub import HfApi, hf_hub_download
    token = os.environ.get("HF_TOKEN") or None
    api = HfApi()
    try:
        files = api.list_repo_files(repo, repo_type="dataset", token=token)
    except Exception as e:
        print(f"[img] cannot list {repo}: {e}")
        return 0
    imgs = [f for f in files if f.lower().endswith(IMAGE_EXTS)]
    print(f"[img] {repo}: {len(imgs)} images, taking up to {limit} new")
    added = 0
    for f in imgs:
        if added >= limit:
            break
        tag = f"hf:{repo}:{os.path.basename(f)}"
        if tag in seen:
            continue
        try:
            local = hf_hub_download(repo, f, repo_type="dataset", token=token)
            vec = image_feature_vector(local)
            add_sample(vec, is_ai, tag)
            seen.add(tag)
            added += 1
            os.unlink(local)
        except Exception as e:
            print(f"    x {f}: {e}")
    print(f"[img] {repo}: +{added} {'AI' if is_ai else 'real'}")
    return added


def _label_is_ai(value, class_names=None) -> Optional[bool]:
    """Map a dataset label value to AI(True)/real(False). Handles string labels
    and ClassLabel ints (via class_names)."""
    s = None
    if class_names and isinstance(value, int) and 0 <= value < len(class_names):
        s = str(class_names[value]).lower()
    elif isinstance(value, str):
        s = value.lower()
    if s is not None:
        if any(t in s for t in ("ai", "fake", "synthetic", "generat", "gan", "diffus")):
            return True
        if any(t in s for t in ("real", "authentic", "camera", "human", "natural")):
            return False
        return None
    # numeric with no class names: can't know the convention — skip (logged once)
    return None


def collect_hf_labeled(repo: str, limit: int, seen: set) -> int:
    """Collect from a single HF image dataset that carries BOTH classes via a
    label column (the common format). Uses the datasets library so parquet /
    imagefolder / webdataset all work. Logs the schema on the first example so
    the label mapping is transparent in the run logs."""
    import tempfile
    from datasets import load_dataset
    token = os.environ.get("HF_TOKEN") or None
    try:
        ds = load_dataset(repo, split="train", streaming=True, token=token)
    except Exception as e:
        print(f"[img] load {repo}: {e}")
        return 0

    # discover the label column + its class names (if any)
    label_key = None
    class_names = None
    try:
        feats = getattr(ds, "features", None) or {}
        for k in ("label", "labels", "target", "class", "is_ai", "ai", "y"):
            if k in feats:
                label_key = k
                cn = getattr(feats[k], "names", None)
                class_names = list(cn) if cn else None
                break
        print(f"[img] {repo}: features={list(feats.keys())} label_key={label_key} classes={class_names}")
    except Exception:
        pass

    img_key = None
    added = 0
    for i, ex in enumerate(ds):
        if added >= limit:
            break
        if img_key is None:
            for k in ("image", "img", "images", "picture"):
                if k in ex:
                    img_key = k
                    break
            if img_key is None:
                print(f"[img] {repo}: no image column in {list(ex.keys())}")
                return added
        lv = ex.get(label_key) if label_key else None
        is_ai = _label_is_ai(lv, class_names)
        if is_ai is None:
            if i == 0:
                print(f"[img] {repo}: unmapped label value={lv!r} — skipping repo")
            continue
        tag = f"hf:{repo}:{i}"
        if tag in seen:
            continue
        try:
            img = ex[img_key]
            tmp = tempfile.mktemp(suffix=".png")
            img.convert("RGB").save(tmp)
            vec = image_feature_vector(tmp)
            add_sample(vec, is_ai, tag)
            seen.add(tag)
            added += 1
            os.unlink(tmp)
        except Exception as e:
            if i < 3:
                print(f"    x ex{i}: {e}")
    print(f"[img] {repo}: +{added} labeled samples")
    return added


def train_image_model() -> dict:
    import numpy as np
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score

    samples = _load()
    y = np.array([s["label"] for s in samples])
    if len(samples) < 20 or int(y.sum()) < 5 or int((1 - y).sum()) < 5:
        return {"error": f"need >=5 of each class, have {len(samples)} ({int(y.sum())} AI)"}
    X = np.array([s["features"] for s in samples])
    method = "isotonic" if len(samples) >= 400 else "sigmoid"
    pipe = Pipeline([
        ("scale", StandardScaler()),
        ("clf", CalibratedClassifierCV(
            GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                       learning_rate=0.05, subsample=0.8, random_state=42),
            method=method, cv=3)),
    ])
    cv = StratifiedKFold(n_splits=min(5, len(samples) // 4), shuffle=True, random_state=42)
    oof = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
    pred = oof >= 0.5
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    pipe.fit(X, y)
    import joblib
    joblib.dump(pipe, MODEL)
    meta = {
        "samples": len(samples), "ai_samples": int(y.sum()), "real_samples": int((1 - y).sum()),
        "feature_keys": _IMG_FEATURE_KEYS,
        "cv_auc": float(roc_auc_score(y, oof)),
        "cv_precision": tp / (tp + fp) if (tp + fp) else None,
        "cv_recall": tp / (tp + fn) if (tp + fn) else None,
        "cv_fpr": fp / (fp + tn) if (fp + tn) else None,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    META.write_text(json.dumps(meta))
    print(f"[img] trained: {meta['samples']} samples, AUC {meta['cv_auc']:.3f}, FPR {meta['cv_fpr']}")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai-repos", default="")       # single-class repos (all AI)
    ap.add_argument("--real-repos", default="")     # single-class repos (all real)
    ap.add_argument("--labeled-repos", default="")  # one repo, both classes via a label column
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()
    seen = _seen()
    total = 0
    for repo in [r.strip() for r in args.labeled_repos.split(",") if r.strip()]:
        total += collect_hf_labeled(repo, args.limit, seen)
    for repo in [r.strip() for r in args.ai_repos.split(",") if r.strip()]:
        total += collect_hf(repo, True, args.limit, seen)
    for repo in [r.strip() for r in args.real_repos.split(",") if r.strip()]:
        total += collect_hf(repo, False, args.limit, seen)
    print(f"[img] collected {total} new samples")
    if total:
        train_image_model()


if __name__ == "__main__":
    main()
