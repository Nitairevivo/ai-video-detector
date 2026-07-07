"""
Accuracy evaluation harness for the detection ensemble.

Runs the FULL pipeline (metadata → Gemini-base ensemble) over the labeled
dataset and reports accuracy / precision / recall / confusion matrix, plus a
per-layer breakdown so we can see which layer helps.

    python evaluate.py                      # 40 per class, uses Gemini if key set
    python evaluate.py --limit 100          # 100 per class
    python evaluate.py --no-gemini          # test fusion without Gemini
    python evaluate.py --threshold 0.5      # AI decision threshold

Dataset:
    /Users/nitai/Desktop/dataset/AI_Videos    → label = AI
    /Users/nitai/Desktop/dataset/Real_Videos  → label = real
Override with --ai-dir / --real-dir.
"""
import argparse
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyzer import extract_features
from analyzer.ensemble import analyze_ensemble
from models.classifier import get_classifier

EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def list_videos(d: Path, limit: int, seed: int):
    files = [f for f in d.glob("*") if f.suffix.lower() in EXTS and f.stat().st_size > 10000]
    random.Random(seed).shuffle(files)
    return files[:limit]


def predict(path: str, use_gemini: bool, threshold: float):
    result = extract_features(path, deep=True)
    classifier = get_classifier()
    ml_prob, _ = classifier.predict(result.feature_vector)
    ens = analyze_ensemble(path, result, ml_prob, use_gemini=use_gemini)
    is_ai = ens.confidence >= threshold
    return is_ai, ens


def run(ai_dir, real_dir, limit, use_gemini, threshold, seed):
    samples = []
    for f in list_videos(Path(ai_dir), limit, seed):
        samples.append((f, True))
    for f in list_videos(Path(real_dir), limit, seed):
        samples.append((f, False))
    random.Random(seed).shuffle(samples)

    if not samples:
        print("No videos found. Check --ai-dir / --real-dir.")
        return

    tp = tn = fp = fn = 0
    layer_hits = {}   # layer -> [correct, total] when that layer voted
    errors = []
    t0 = time.time()

    print(f"Evaluating {len(samples)} videos "
          f"({'with' if use_gemini else 'WITHOUT'} Gemini, threshold={threshold})\n")

    for i, (path, is_ai_true) in enumerate(samples, 1):
        try:
            pred_ai, ens = predict(str(path), use_gemini, threshold)
        except Exception as e:
            print(f"  [{i}/{len(samples)}] ERROR {path.name[:40]}: {e}")
            continue

        if is_ai_true and pred_ai:      tp += 1; ok = True
        elif is_ai_true and not pred_ai: fn += 1; ok = False
        elif not is_ai_true and pred_ai: fp += 1; ok = False
        else:                            tn += 1; ok = True

        for layer in (ens.layers or {}):
            rec = layer_hits.setdefault(layer, [0, 0])
            rec[1] += 1
            if ok:
                rec[0] += 1

        mark = "✓" if ok else "✗"
        truth = "AI  " if is_ai_true else "real"
        if not ok:
            errors.append((path.name, truth, ens.confidence, ens.method))
        print(f"  [{i}/{len(samples)}] {mark} truth={truth} "
              f"pred={ens.confidence*100:4.0f}%AI  {path.name[:34]}")

    total = tp + tn + fp + fn
    if total == 0:
        print("No successful evaluations.")
        return
    acc = (tp + tn) / total
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0

    print("\n" + "=" * 52)
    print(f"  Samples evaluated : {total}   ({time.time()-t0:.0f}s)")
    print(f"  Accuracy          : {acc*100:.1f}%")
    print(f"  Precision (AI)    : {prec*100:.1f}%   (of flagged AI, how many right)")
    print(f"  Recall (AI)       : {rec*100:.1f}%   (of real AI, how many caught)")
    print(f"  F1                : {f1*100:.1f}%")
    print(f"\n  Confusion matrix")
    print(f"                 pred AI   pred real")
    print(f"    true AI       {tp:5d}     {fn:6d}")
    print(f"    true real     {fp:5d}     {tn:6d}")
    print(f"\n  False positives (real flagged as AI): {fp}")
    print(f"  False negatives (AI missed)          : {fn}")

    print(f"\n  Per-layer accuracy when it voted:")
    for layer, (c, t) in sorted(layer_hits.items(), key=lambda x: -x[1][1]):
        print(f"    {layer:16s} {c/t*100:5.1f}%  ({t} votes)")

    if errors:
        print(f"\n  Sample mistakes:")
        for name, truth, conf, method in errors[:12]:
            print(f"    {truth}  {conf*100:3.0f}%AI  {name[:30]:30s}  {method[:44]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ai-dir", default="/Users/nitai/Desktop/dataset/AI_Videos")
    p.add_argument("--real-dir", default="/Users/nitai/Desktop/dataset/Real_Videos")
    p.add_argument("--limit", type=int, default=40, help="videos per class")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--no-gemini", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    run(args.ai_dir, args.real_dir, args.limit,
        use_gemini=not args.no_gemini, threshold=args.threshold, seed=args.seed)
