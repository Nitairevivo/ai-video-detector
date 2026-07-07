"""
VerifAI Real-World Benchmark (Roadmap phase 0.1)

Unlike benchmark.py / benchmark_v2.py — which tried to download videos on the
server and always failed on platform IP blocks — this runner works on LOCAL
files collected via the phone (Share Intent → save) or any other means.
The download problem and the measurement problem are now separate.

Usage:
    # 1. Put videos in a folder and describe them in a manifest (CSV or JSON):
    #
    #    manifest.csv:
    #      filename,label,platform,category
    #      kling_dragon.mp4,ai,tiktok,animals
    #      grandma_kitchen.mp4,real,tiktok,people
    #      flour_challenge.mp4,real,instagram,chaotic   <- hard negatives matter!
    #
    # 2. Run:
    #      python tests/real_benchmark.py /path/to/videos --manifest manifest.csv
    #
    #    Flags:
    #      --no-gemini   skip the Gemini layer (no API key / cost-free run)
    #      --shallow     metadata/codec layers only (fast smoke test)
    #      --out DIR     where to write reports (default: tests/)
    #
    # 3. Read the report:
    #      tests/real_benchmark_results.json   (machine-readable, every video)
    #      tests/real_benchmark_report.md      (human-readable summary)

The report answers the questions an enterprise buyer asks:
  precision / recall / FPR / FNR / accuracy, confusion matrix,
  breakdown by platform, by category, and by which layer decided.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


# ── Manifest loading ──────────────────────────────────────────────────────────

def load_manifest(path: Path) -> list:
    """
    Returns a list of {filename, label, platform, category} dicts.
    label must be 'ai' or 'real' (case-insensitive). platform/category optional.
    """
    rows = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else data.get("videos", [])
        for it in items:
            rows.append({
                "filename": it["filename"],
                "label": str(it["label"]).strip().lower(),
                "platform": str(it.get("platform", "unknown")).strip().lower(),
                "category": str(it.get("category", "unknown")).strip().lower(),
            })
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for it in csv.DictReader(f):
                if not it.get("filename"):
                    continue
                rows.append({
                    "filename": it["filename"].strip(),
                    "label": (it.get("label") or "").strip().lower(),
                    "platform": (it.get("platform") or "unknown").strip().lower(),
                    "category": (it.get("category") or "unknown").strip().lower(),
                })

    bad = [r for r in rows if r["label"] not in ("ai", "real")]
    if bad:
        names = ", ".join(r["filename"] for r in bad[:5])
        raise SystemExit(f"Manifest error: label must be 'ai' or 'real' — bad rows: {names}")
    return rows


# ── Single-video evaluation ───────────────────────────────────────────────────

def evaluate_video(video_path: str, deep: bool, use_gemini: bool) -> dict:
    """Run the same pipeline as the production server on one local file."""
    from analyzer import extract_features
    from analyzer.ensemble import analyze_ensemble
    from models.classifier import get_classifier

    t0 = time.time()
    result = extract_features(video_path, deep=deep)
    ml_prob, _ = get_classifier().predict(result.feature_vector)
    ens = analyze_ensemble(video_path, result, ml_prob, use_gemini=use_gemini)
    return {
        "verdict": ens.verdict,
        "confidence": round(float(ens.confidence), 4),
        "predicted_ai": ens.verdict == "ai_generated",
        "method": ens.method,
        "layers": ens.layers,
        "ai_tool": result.ai_tool,
        "elapsed_s": round(time.time() - t0, 2),
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(results: list) -> dict:
    tp = sum(1 for r in results if r["expected_ai"] and r["predicted_ai"])
    fn = sum(1 for r in results if r["expected_ai"] and not r["predicted_ai"])
    fp = sum(1 for r in results if not r["expected_ai"] and r["predicted_ai"])
    tn = sum(1 for r in results if not r["expected_ai"] and not r["predicted_ai"])
    n = tp + fn + fp + tn

    def safe(a, b):
        return round(a / b, 4) if b else None

    return {
        "total": n,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "accuracy": safe(tp + tn, n),
        "precision": safe(tp, tp + fp),
        "recall": safe(tp, tp + fn),
        "fpr": safe(fp, fp + tn),
        "fnr": safe(fn, fn + tp),
    }


def breakdown(results: list, key: str) -> dict:
    groups = defaultdict(list)
    for r in results:
        groups[r.get(key, "unknown")].append(r)
    return {k: compute_metrics(v) for k, v in sorted(groups.items())}


def method_breakdown(results: list) -> dict:
    """Which decision layer produced each verdict, and how often it was right."""
    groups = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in results:
        # First words of the method string identify the deciding layer well enough
        layer = (r.get("method") or "unknown").split(":")[0].split("(")[0].strip()[:60]
        groups[layer]["n"] += 1
        groups[layer]["correct"] += int(r["correct"])
    return {k: {**v, "accuracy": round(v["correct"] / v["n"], 3)}
            for k, v in sorted(groups.items(), key=lambda kv: -kv[1]["n"])}


# ── Report rendering ──────────────────────────────────────────────────────────

def _pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def render_markdown(metrics, by_platform, by_category, by_method, errors, skipped, args_desc) -> str:
    c = metrics["confusion"]
    lines = [
        "# VerifAI Real-World Benchmark Report",
        "",
        f"*Run config: {args_desc}*",
        "",
        "## Headline numbers",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Videos tested | {metrics['total']} |",
        f"| **Accuracy** | **{_pct(metrics['accuracy'])}** |",
        f"| **Precision** (flagged AI → really AI) | **{_pct(metrics['precision'])}** |",
        f"| **Recall** (AI videos caught) | **{_pct(metrics['recall'])}** |",
        f"| **False-positive rate** (real flagged as AI) | **{_pct(metrics['fpr'])}** |",
        f"| False-negative rate | {_pct(metrics['fnr'])} |",
        "",
        f"Confusion: TP={c['tp']}  FP={c['fp']}  FN={c['fn']}  TN={c['tn']}"
        + (f"  |  skipped (unreadable/missing): {skipped}" if skipped else ""),
        "",
        "## By platform",
        "",
        "| Platform | N | Accuracy | Precision | Recall | FPR |",
        "|---|---|---|---|---|---|",
    ]
    for k, m in by_platform.items():
        lines.append(f"| {k} | {m['total']} | {_pct(m['accuracy'])} | "
                     f"{_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['fpr'])} |")
    lines += ["", "## By category", "",
              "| Category | N | Accuracy | Precision | Recall | FPR |",
              "|---|---|---|---|---|---|"]
    for k, m in by_category.items():
        lines.append(f"| {k} | {m['total']} | {_pct(m['accuracy'])} | "
                     f"{_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['fpr'])} |")
    lines += ["", "## By deciding layer", "",
              "| Layer | Decisions | Correct | Accuracy |",
              "|---|---|---|---|"]
    for k, m in by_method.items():
        lines.append(f"| {k} | {m['n']} | {m['correct']} | {m['accuracy'] * 100:.1f}% |")

    lines += ["", "## Misclassified videos", ""]
    if not errors:
        lines.append("None 🎉")
    else:
        lines += ["| File | Expected | Predicted | Confidence | Method |",
                  "|---|---|---|---|---|"]
        for r in errors:
            lines.append(f"| {r['filename']} | {'AI' if r['expected_ai'] else 'REAL'} | "
                         f"{'AI' if r['predicted_ai'] else 'REAL'} | {r['confidence']:.0%} | "
                         f"{(r.get('method') or '')[:60]} |")
    lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="VerifAI real-world benchmark on local video files")
    ap.add_argument("videos_dir", help="Folder containing the collected video files")
    ap.add_argument("--manifest", required=True, help="CSV/JSON manifest with filename,label[,platform,category]")
    ap.add_argument("--no-gemini", action="store_true", help="Skip the Gemini layer")
    ap.add_argument("--shallow", action="store_true", help="Metadata/codec layers only (fast)")
    ap.add_argument("--out", default=str(Path(__file__).parent), help="Output directory for reports")
    args = ap.parse_args()

    videos_dir = Path(args.videos_dir)
    if not videos_dir.is_dir():
        raise SystemExit(f"Not a directory: {videos_dir}")
    manifest = load_manifest(Path(args.manifest))
    if not manifest:
        raise SystemExit("Manifest is empty")

    use_gemini = not args.no_gemini
    if use_gemini and not os.environ.get("GEMINI_API_KEY"):
        print("NOTE: GEMINI_API_KEY not set — falling back to --no-gemini mode.\n")
        use_gemini = False
    deep = not args.shallow

    n_ai = sum(1 for r in manifest if r["label"] == "ai")
    print("=" * 72)
    print(f"  VerifAI Real-World Benchmark — {len(manifest)} videos "
          f"({n_ai} AI / {len(manifest) - n_ai} real)")
    print(f"  deep={deep}  gemini={use_gemini}")
    print("=" * 72)

    results, skipped = [], 0
    for i, row in enumerate(manifest, 1):
        fpath = videos_dir / row["filename"]
        tag = f"[{i:3d}/{len(manifest)}] {row['filename'][:40]:<40}"
        if not fpath.is_file() or fpath.suffix.lower() not in VIDEO_EXTS:
            print(f"{tag} ⚠️  missing/unsupported — skipped")
            skipped += 1
            continue
        try:
            r = evaluate_video(str(fpath), deep=deep, use_gemini=use_gemini)
        except Exception as e:
            print(f"{tag} ⚠️  error: {str(e)[:50]} — skipped")
            skipped += 1
            continue

        expected_ai = row["label"] == "ai"
        r.update({
            "filename": row["filename"],
            "platform": row["platform"],
            "category": row["category"],
            "expected_ai": expected_ai,
            "correct": r["predicted_ai"] == expected_ai,
        })
        results.append(r)
        icon = "✅" if r["correct"] else "❌"
        print(f"{tag} {icon} {'AI  ' if r['predicted_ai'] else 'REAL'} "
              f"({r['confidence']:.0%}) [{r['elapsed_s']}s]")

    if not results:
        raise SystemExit("\nNo videos were evaluated — check paths in the manifest.")

    metrics = compute_metrics(results)
    by_platform = breakdown(results, "platform")
    by_category = breakdown(results, "category")
    by_method = method_breakdown(results)
    errors = [r for r in results if not r["correct"]]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "real_benchmark_results.json").write_text(json.dumps({
        "config": {"deep": deep, "gemini": use_gemini},
        "metrics": metrics,
        "by_platform": by_platform,
        "by_category": by_category,
        "by_deciding_layer": by_method,
        "results": results,
    }, indent=2, ensure_ascii=False))

    args_desc = (f"{metrics['total']} videos, deep={deep}, gemini={use_gemini}, "
                 f"skipped={skipped}")
    report_md = render_markdown(metrics, by_platform, by_category, by_method,
                                errors, skipped, args_desc)
    (out / "real_benchmark_report.md").write_text(report_md)

    print("\n" + "=" * 72)
    print(f"  Accuracy:  {_pct(metrics['accuracy'])}    Precision: {_pct(metrics['precision'])}")
    print(f"  Recall:    {_pct(metrics['recall'])}    FPR:       {_pct(metrics['fpr'])}")
    print(f"  Misclassified: {len(errors)}   Skipped: {skipped}")
    print(f"\n  Full report: {out / 'real_benchmark_report.md'}")
    print("=" * 72)


if __name__ == "__main__":
    main()
