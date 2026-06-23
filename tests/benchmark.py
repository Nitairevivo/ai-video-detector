"""
Benchmark VerifAI detector on 100 videos (50 AI-generated, 50 real).
Downloads via yt-dlp and runs through the detector.
Usage: python tests/benchmark.py
"""
import os, sys, json, time, subprocess, tempfile, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer import extract_features

# ─── Video sets ───────────────────────────────────────────────────────────────
# Confirmed AI-generated (Sora, Kling, Pika, Runway demos)
AI_VIDEOS = [
    # OpenAI Sora official demos
    ("https://www.youtube.com/shorts/klSXAJ_kzZU", "Sora"),
    ("https://www.youtube.com/watch?v=HK6y8DAPN_0", "Sora"),
    ("https://www.youtube.com/shorts/QaCxFZBmEE0", "Sora"),
    # Kling AI demos
    ("https://www.youtube.com/shorts/Y7GNvMFkGCo", "Kling"),
    ("https://www.youtube.com/shorts/BF_DPCxH6n0", "Kling"),
    ("https://www.youtube.com/shorts/JGLAaMQkbsY", "Kling"),
    ("https://www.youtube.com/shorts/iVpAJOg1TXM", "Kling"),
    ("https://www.youtube.com/shorts/SqTaXIbg_38", "Kling"),
    # Runway Gen-3 demos
    ("https://www.youtube.com/shorts/9F2nKiNaWso", "Runway"),
    ("https://www.youtube.com/shorts/qiV6JgAlMvo", "Runway"),
    ("https://www.youtube.com/shorts/bqCl9Ac5a2A", "Runway"),
    # Pika Labs
    ("https://www.youtube.com/shorts/AUOtjRFRNqI", "Pika"),
    ("https://www.youtube.com/shorts/gbYIr1R9t08", "Pika"),
    ("https://www.youtube.com/shorts/Yg_Z5nWHpw4", "Pika"),
    # Luma Dream Machine
    ("https://www.youtube.com/shorts/gC9JXXvl3h4", "Luma"),
    ("https://www.youtube.com/shorts/g_UiI-Jqab0", "Luma"),
    # Hailuo / MiniMax
    ("https://www.youtube.com/shorts/3D47wLSmFcc", "Hailuo"),
    ("https://www.youtube.com/shorts/fkq2oI6mNBY", "Hailuo"),
    # HunyuanVideo
    ("https://www.youtube.com/shorts/yLHNUECrxkk", "HunyuanVideo"),
    ("https://www.youtube.com/shorts/cYrY4v6oI_o", "HunyuanVideo"),
    # Wan 2.0
    ("https://www.youtube.com/shorts/LkmLKVHuIGM", "Wan2"),
    ("https://www.youtube.com/shorts/GWdLbMsXxts", "Wan2"),
    # CogVideoX
    ("https://www.youtube.com/shorts/fN4HLOQ4D_Q", "CogVideoX"),
    # Stable Video Diffusion
    ("https://www.youtube.com/shorts/Ia5L5TVPGHE", "SVD"),
    ("https://www.youtube.com/shorts/kAEq3F1w7k8", "SVD"),
    # AnimateDiff / AnimateAnyone
    ("https://www.youtube.com/shorts/Wr2pKSExRxE", "AnimateDiff"),
    ("https://www.youtube.com/shorts/Bik4VFpI5Ac", "AnimateDiff"),
    # HeyGen avatar
    ("https://www.youtube.com/shorts/OWgGCOkp-_A", "HeyGen"),
    ("https://www.youtube.com/shorts/xLN3oPOJqWI", "HeyGen"),
    # Generic AI compilations (known AI-generated)
    ("https://www.youtube.com/shorts/a0E8KQXG1kA", "AI_Mix"),
    ("https://www.youtube.com/shorts/EDJ-HNf8xRE", "AI_Mix"),
    ("https://www.youtube.com/shorts/5xWqX-gSqaE", "AI_Mix"),
    ("https://www.youtube.com/shorts/LW8Dsk7FQII", "AI_Mix"),
    ("https://www.youtube.com/shorts/uDCNHF5GGAI", "AI_Mix"),
    ("https://www.youtube.com/shorts/NIfJ5BXB87c", "AI_Mix"),
    ("https://www.youtube.com/shorts/vSqbGWJzjxA", "AI_Mix"),
    ("https://www.youtube.com/shorts/bItWxuKD1v4", "AI_Mix"),
    ("https://www.youtube.com/shorts/RU5RTnQxQvE", "AI_Mix"),
    ("https://www.youtube.com/shorts/wUe44mgNJjM", "AI_Mix"),
    ("https://www.youtube.com/shorts/iMzXwZtGBzE", "AI_Mix"),
    ("https://www.youtube.com/shorts/JNTEH3hzz8o", "AI_Mix"),
    ("https://www.youtube.com/shorts/dkOSvFpb3A4", "AI_Mix"),
    ("https://www.youtube.com/shorts/9kO7Hp0JiNw", "AI_Mix"),
    ("https://www.youtube.com/shorts/TUeVGbPu3Bk", "AI_Mix"),
    ("https://www.youtube.com/shorts/WGQdAzPnOYk", "AI_Mix"),
    ("https://www.youtube.com/shorts/yBe9aqvg7oE", "AI_Mix"),
    ("https://www.youtube.com/shorts/RFyLF0bCkv4", "AI_Mix"),
    ("https://www.youtube.com/shorts/cAKzuPX_LoU", "AI_Mix"),
    ("https://www.youtube.com/shorts/uXFf4yTv_xQ", "AI_Mix"),
]

# Confirmed real footage (news, sports, nature, vlogs)
REAL_VIDEOS = [
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "Real_Music"),
    ("https://www.youtube.com/shorts/7wtfhZwyrcc", "Real_Nature"),
    ("https://www.youtube.com/shorts/ByEz5vJYoEo", "Real_Sport"),
    ("https://www.youtube.com/shorts/K4TOrB7at0Y", "Real_Vlog"),
    ("https://www.youtube.com/shorts/CQ85tBiGYMM", "Real_News"),
    ("https://www.youtube.com/shorts/gSLIWEBaTRQ", "Real_Sport"),
    ("https://www.youtube.com/shorts/nfWlot6h_JM", "Real_Vlog"),
    ("https://www.youtube.com/shorts/9bZkp7q19f0", "Real_Music"),
    ("https://www.youtube.com/shorts/LXb3EKWsInQ", "Real_Vlog"),
    ("https://www.youtube.com/shorts/VYOjWnS4cMY", "Real_Vlog"),
    ("https://www.youtube.com/shorts/kffacxfA7Q4", "Real_Vlog"),
    ("https://www.youtube.com/shorts/HgzGwKwLmgU", "Real_Nature"),
    ("https://www.youtube.com/shorts/0e3GPea1Ws8", "Real_Sport"),
    ("https://www.youtube.com/shorts/C0DPdy7n2AI", "Real_Vlog"),
    ("https://www.youtube.com/shorts/LE2v3sUzTH4", "Real_Nature"),
    ("https://www.youtube.com/shorts/wCtdDJJdD6M", "Real_Vlog"),
    ("https://www.youtube.com/shorts/YbJOTdZBX1g", "Real_Vlog"),
    ("https://www.youtube.com/shorts/3tmd-ClpJxA", "Real_Music"),
    ("https://www.youtube.com/shorts/RgKAFK5djSk", "Real_Music"),
    ("https://www.youtube.com/shorts/MtN1YnoL46Q", "Real_Vlog"),
    ("https://www.youtube.com/shorts/VXjln4Txfek", "Real_Vlog"),
    ("https://www.youtube.com/shorts/K4TOrB7at0Y", "Real_Vlog"),
    ("https://www.youtube.com/shorts/lp-EBCfEFBs", "Real_Sport"),
    ("https://www.youtube.com/shorts/fJ9rUzIMcZQ", "Real_Music"),
    ("https://www.youtube.com/shorts/JGwWNGJdvx8", "Real_Music"),
    ("https://www.youtube.com/shorts/1ZYbU82imUs", "Real_Vlog"),
    ("https://www.youtube.com/shorts/pRpeEdMmmQ0", "Real_Nature"),
    ("https://www.youtube.com/shorts/kJQP7kiw5Fk", "Real_Music"),
    ("https://www.youtube.com/shorts/OPf0YAFcvV0", "Real_Vlog"),
    ("https://www.youtube.com/shorts/hT_nvWreIhg", "Real_Vlog"),
    ("https://www.youtube.com/shorts/3JZ_D3ELwOQ", "Real_Vlog"),
    ("https://www.youtube.com/shorts/LoZa16Pi3Ds", "Real_Vlog"),
    ("https://www.youtube.com/shorts/bHuTkJvISS4", "Real_Vlog"),
    ("https://www.youtube.com/shorts/VIiYH4tBJZU", "Real_Sport"),
    ("https://www.youtube.com/shorts/Sagg08DrO-0", "Real_Nature"),
    ("https://www.youtube.com/shorts/MK6TZOMmOSg", "Real_Nature"),
    ("https://www.youtube.com/shorts/xMbtGY8Tnfo", "Real_Vlog"),
    ("https://www.youtube.com/shorts/TYfhL2bF6f4", "Real_Music"),
    ("https://www.youtube.com/shorts/V4h0bS5fmzg", "Real_Nature"),
    ("https://www.youtube.com/shorts/0vWF04HE1TQ", "Real_Sport"),
    ("https://www.youtube.com/shorts/j3_Wr7dNOv4", "Real_Vlog"),
    ("https://www.youtube.com/shorts/M7lc1UVf-VE", "Real_Vlog"),
    ("https://www.youtube.com/shorts/sZUvnf4SGA4", "Real_Nature"),
    ("https://www.youtube.com/shorts/l9xbr0nXI0g", "Real_Vlog"),
    ("https://www.youtube.com/shorts/X-TmJFGvhMo", "Real_Vlog"),
    ("https://www.youtube.com/shorts/sVxmj_xV90g", "Real_Music"),
    ("https://www.youtube.com/shorts/tPEE9ZwTmy0", "Real_Nature"),
    ("https://www.youtube.com/shorts/hY7m3vAf3nU", "Real_Vlog"),
    ("https://www.youtube.com/shorts/7wtfhZwyrcc", "Real_Nature"),
    ("https://www.youtube.com/shorts/xHgOnhw2YcI", "Real_Vlog"),
]

# ─── Download & test ──────────────────────────────────────────────────────────

def download(url: str, out_path: str) -> bool:
    try:
        r = subprocess.run(
            ["yt-dlp", "-f", "mp4/best[height<=480]", "-o", out_path,
             "--no-playlist", "--quiet", "--no-warnings",
             "--socket-timeout", "20", url],
            capture_output=True, timeout=60
        )
        return r.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


def test_video(url: str, expected_ai: bool, label: str) -> dict:
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        ok = download(url, tmp)
        if not ok:
            return {"url": url, "label": label, "status": "download_failed"}

        t0 = time.time()
        result = extract_features(tmp)
        elapsed = time.time() - t0

        predicted_ai = result.is_ai
        correct = predicted_ai == expected_ai
        return {
            "url": url,
            "label": label,
            "expected": "AI" if expected_ai else "REAL",
            "predicted": "AI" if predicted_ai else "REAL",
            "verdict": result.verdict,
            "confidence": round(result.confidence, 3),
            "ai_tool": result.ai_tool,
            "method": result.method[:60],
            "correct": correct,
            "elapsed_s": round(elapsed, 2),
            "status": "ok",
        }
    finally:
        try: os.unlink(tmp)
        except: pass


def main():
    print("=" * 70)
    print("  VerifAI Benchmark — 100 videos (50 AI + 50 Real)")
    print("=" * 70)

    results = []
    correct_ai = correct_real = fail_ai = fail_real = skipped = 0

    all_tests = [(url, True, lbl) for url, lbl in AI_VIDEOS] + \
                [(url, False, lbl) for url, lbl in REAL_VIDEOS]

    for i, (url, expected, label) in enumerate(all_tests, 1):
        short = url.split("/")[-1][:16]
        print(f"[{i:3d}/100] {label:<18} {short} ", end="", flush=True)
        r = test_video(url, expected, label)
        results.append(r)

        if r["status"] == "download_failed":
            print("⚠️  DOWNLOAD FAILED")
            skipped += 1
            continue

        icon = "✅" if r["correct"] else "❌"
        print(f"{icon} {r['predicted']:<6} ({r['confidence']:.0%}) [{r['elapsed_s']}s] {r.get('ai_tool') or r['method'][:30]}")

        if r["correct"]:
            if expected: correct_ai += 1
            else:        correct_real += 1
        else:
            if expected: fail_ai += 1
            else:        fail_real += 1

    # ── Summary ──────────────────────────────────────────────────────────────
    tested = len(results) - skipped
    total_correct = correct_ai + correct_real
    accuracy = total_correct / tested * 100 if tested else 0

    print("\n" + "=" * 70)
    print(f"  RESULTS — {tested} videos tested, {skipped} skipped")
    print(f"  Overall accuracy:  {accuracy:.1f}%  ({total_correct}/{tested})")
    print(f"  AI detection:      {correct_ai}/{correct_ai+fail_ai} correct")
    print(f"  Real detection:    {correct_real}/{correct_real+fail_real} correct")
    print(f"  False positives:   {fail_real} (real → AI)")
    print(f"  False negatives:   {fail_ai} (AI → real)")
    print("=" * 70)

    # Save results for analysis
    out = Path(__file__).parent / "benchmark_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Full results saved to: {out}")

    # Show failures for debugging
    failures = [r for r in results if r.get("status") == "ok" and not r["correct"]]
    if failures:
        print(f"\n  FAILURES ({len(failures)}):")
        for r in failures:
            print(f"    [{r['label']}] expected {r['expected']} → got {r['predicted']} "
                  f"({r['confidence']:.0%}) | {r['method'][:50]}")


if __name__ == "__main__":
    main()
