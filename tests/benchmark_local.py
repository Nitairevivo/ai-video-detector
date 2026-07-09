"""
Local benchmark — point it at your two folders and get the full accuracy number.

You collected AI videos and real videos into two folders on your own machine
(where the videos actually live — the cloud agent can't reach your disk). This
builds the manifest for you and runs the complete detection pipeline, printing
precision / recall / FPR / accuracy plus a saved report.

Usage (from the repo root, on your Mac):

    python tests/benchmark_local.py --ai-dir ~/Desktop/ai_test --real-dir ~/Desktop/real_test

    # faster, no Gemini cost:
    python tests/benchmark_local.py --ai-dir ... --real-dir ... --no-gemini

    # to include the Gemini vision layer (best accuracy), set your key first:
    export GEMINI_API_KEY=your_key
    python tests/benchmark_local.py --ai-dir ... --real-dir ...

Every video file in --ai-dir is labeled AI, every file in --real-dir is labeled
real. Any format ffmpeg reads works (mp4/mov/webm/mkv/…).
"""
import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ogv", ".3gp"}


def _videos(folder: Path):
    if not folder.is_dir():
        raise SystemExit(f"Not a folder: {folder}")
    return [p for p in sorted(folder.iterdir())
            if p.suffix.lower() in VIDEO_EXTS and p.stat().st_size > 10000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai-dir", required=True, help="Folder of AI-generated videos")
    ap.add_argument("--real-dir", required=True, help="Folder of real videos")
    ap.add_argument("--no-gemini", action="store_true")
    ap.add_argument("--shallow", action="store_true", help="metadata/codec only (fast smoke test)")
    ap.add_argument("--out", default=str(Path(__file__).parent))
    args = ap.parse_args()

    ai = _videos(Path(args.ai_dir).expanduser())
    real = _videos(Path(args.real_dir).expanduser())
    if not ai and not real:
        raise SystemExit("Both folders are empty — add videos first.")
    print(f"Found {len(ai)} AI videos and {len(real)} real videos.")

    # Stage everything into one folder + a generated manifest, then reuse the
    # existing real_benchmark runner so the logic stays in one place.
    stage = Path(tempfile.mkdtemp(prefix="verifai_bench_"))
    vids = stage / "videos"
    vids.mkdir()
    rows = []
    for label, files in (("ai", ai), ("real", real)):
        for i, src in enumerate(files):
            dest_name = f"{label}_{i}_{src.name}".replace(" ", "_")
            (vids / dest_name).write_bytes(src.read_bytes())
            rows.append({"filename": dest_name, "label": label,
                         "platform": "local", "category": label})

    manifest = stage / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "label", "platform", "category"])
        w.writeheader()
        w.writerows(rows)

    cmd = [sys.executable, str(Path(__file__).parent / "real_benchmark.py"),
           str(vids), "--manifest", str(manifest), "--out", args.out]
    if args.no_gemini:
        cmd.append("--no-gemini")
    if args.shallow:
        cmd.append("--shallow")
    print("Running the full detection pipeline…\n")
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
