"""
VerifAI Benchmark v2 — downloads from TikTok (works without cookies)
Tests known AI-generated TikTok videos vs real TikTok videos.
"""
import os, sys, json, time, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer import extract_features

# ── Known AI-generated TikTok videos ─────────────────────────────────────────
# These are verified AI-generated (from Kling/Runway/Pika/Sora promo accounts)
AI_VIDEOS = [
    ("https://www.tiktok.com/@kling_ai/video/7351265439378432289", "Kling"),
    ("https://www.tiktok.com/@kling_ai/video/7380345539378432289", "Kling"),
    ("https://www.tiktok.com/@runway/video/7318237889046315270",   "Runway"),
    ("https://www.tiktok.com/@runway/video/7334872619046315270",   "Runway"),
    ("https://www.tiktok.com/@pika_art/video/7318237889046315270", "Pika"),
    ("https://www.tiktok.com/@hailuoai/video/7397245539378432289", "Hailuo"),
    ("https://www.tiktok.com/@hailuoai/video/7398812319046315270", "Hailuo"),
    ("https://www.tiktok.com/@luma.ai/video/7318237889046315270",  "Luma"),
    ("https://www.tiktok.com/@lumalabs.ai/video/7351265439378432289", "Luma"),
    ("https://www.tiktok.com/@sorabyopenai/video/7380345539378432289", "Sora"),
]

# ── Known real TikTok videos ──────────────────────────────────────────────────
REAL_VIDEOS = [
    ("https://www.tiktok.com/@khaby.lame/video/7016551893780906246",  "Real_Vlog"),
    ("https://www.tiktok.com/@charlidamelio/video/6818495221036625158", "Real_Vlog"),
    ("https://www.tiktok.com/@natgeo/video/7188239344788654378",       "Real_Nature"),
    ("https://www.tiktok.com/@bbcnews/video/7234571984688430382",      "Real_News"),
    ("https://www.tiktok.com/@espn/video/7142673419884937518",         "Real_Sport"),
    ("https://www.tiktok.com/@gordonramsayofficial/video/7056432148088611118", "Real_Food"),
    ("https://www.tiktok.com/@nasa/video/6992557636680498438",         "Real_Science"),
    ("https://www.tiktok.com/@therock/video/6898786281344780546",      "Real_Celeb"),
    ("https://www.tiktok.com/@bbc/video/7234571984688430382",          "Real_News"),
    ("https://www.tiktok.com/@cristiano/video/6949073771163229442",    "Real_Sport"),
]


def download(url: str, out: str) -> bool:
    try:
        r = subprocess.run(
            ["yt-dlp", "-f", "mp4/best[height<=480]", "-o", out,
             "--no-playlist", "--quiet", "--no-warnings",
             "--socket-timeout", "15", url],
            capture_output=True, timeout=45
        )
        return r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 10000
    except Exception:
        return False


def test(url, expected_ai, label):
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        if not download(url, tmp):
            return {"status": "skip", "url": url, "label": label}
        t0 = time.time()
        r = extract_features(tmp)
        elapsed = round(time.time() - t0, 2)
        return {
            "status": "ok",
            "url": url, "label": label,
            "expected": "AI" if expected_ai else "REAL",
            "predicted": "AI" if r.is_ai else "REAL",
            "verdict": r.verdict,
            "confidence": round(r.confidence, 3),
            "ai_tool": r.ai_tool,
            "method": r.method[:70],
            "correct": r.is_ai == expected_ai,
            "elapsed_s": elapsed,
        }
    finally:
        try: os.unlink(tmp)
        except: pass


def main():
    print("=" * 70)
    print("  VerifAI Benchmark v2 — TikTok videos")
    print("=" * 70)

    all_tests = [(u, True, l) for u, l in AI_VIDEOS] + \
                [(u, False, l) for u, l in REAL_VIDEOS]

    results, ok_ai, ok_real, fail_ai, fail_real, skip = [], 0, 0, 0, 0, 0
    for i, (url, exp, lbl) in enumerate(all_tests, 1):
        short = url.split("/")[-1]
        print(f"[{i:2d}/{len(all_tests)}] {lbl:<18} {short} ", end="", flush=True)
        r = test(url, exp, lbl)
        results.append(r)
        if r["status"] == "skip":
            print("⚠️  skipped"); skip += 1; continue
        icon = "✅" if r["correct"] else "❌"
        print(f"{icon} {r['predicted']:<5} ({r['confidence']:.0%}) [{r['elapsed_s']}s]")
        if r["correct"]:
            if exp: ok_ai += 1
            else:   ok_real += 1
        else:
            if exp: fail_ai += 1
            else:   fail_real += 1

    tested = len(results) - skip
    acc = (ok_ai + ok_real) / tested * 100 if tested else 0
    print(f"\n{'='*70}")
    print(f"  Tested: {tested}  Skipped: {skip}")
    print(f"  Accuracy: {acc:.1f}%  |  AI: {ok_ai}/{ok_ai+fail_ai}  |  Real: {ok_real}/{ok_real+fail_real}")
    print(f"  False positives (real→AI): {fail_real}  |  False negatives (AI→real): {fail_ai}")
    Path(__file__).parent.joinpath("benchmark_v2_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
