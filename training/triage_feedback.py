"""
Feedback triage — turns user 👍/👎 reports into a review list (roadmap 5.4).

High-confidence DISAGREEMENTS are the gold: the user says we were wrong
exactly where the model was sure. Those are either mislabeled hard cases
(training candidates) or bad users (noise) — a human skims the JSON this
script produces and promotes rows into training samples.

Usage:
    python training/triage_feedback.py                 # writes data/feedback_review.json
    python training/triage_feedback.py --min-conf 0.8  # only very confident mistakes
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import get_conn, feedback_stats

OUT_PATH = Path(__file__).parent.parent / "data" / "feedback_review.json"


def triage(min_conf: float = 0.7) -> dict:
    """
    Returns {stats, disagreements, agreements_sample}.
    Disagreements are sorted most-confident-first — the most damning cases on top.
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, created_at, verdict, confidence, user_says_ai, agrees,
                   method, source, signals_json
            FROM feedback ORDER BY created_at DESC
        """).fetchall()

    disagreements = []
    agree_count = 0
    for r in rows:
        if r["agrees"]:
            agree_count += 1
            continue
        # Distance from the decision boundary = how badly we were wrong (per the user)
        conviction = abs(r["confidence"] - 0.5) * 2
        if r["confidence"] >= min_conf or (1 - r["confidence"]) >= min_conf:
            try:
                signals = json.loads(r["signals_json"] or "{}")
            except Exception:
                signals = {}
            disagreements.append({
                "feedback_id": r["id"],
                "created_at": r["created_at"],
                "we_said": r["verdict"],
                "our_confidence": r["confidence"],
                "user_says": "ai" if r["user_says_ai"] else "real",
                "conviction": round(conviction, 3),
                "method": r["method"],
                "source": r["source"],
                "signals": signals,
                "suggested_label": int(bool(r["user_says_ai"])),
            })

    disagreements.sort(key=lambda d: -d["conviction"])
    return {
        "stats": feedback_stats(),
        "min_conf": min_conf,
        "disagreements": disagreements,
        "note": ("Review each disagreement; to adopt one as a training sample, "
                 "append {features: <ordered vector>, label: suggested_label, "
                 "source: 'feedback:<id>'} to data/training_samples.json and retrain. "
                 "Signals here are the named dict, not the ordered vector — recompute "
                 "features from the original video when possible."),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-conf", type=float, default=0.7,
                    help="Only include mistakes where the model was at least this confident")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    report = triage(args.min_conf)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    s = report["stats"]
    print(f"Feedback total: {s['total']}  |  agreement: {s['agreement_rate']}")
    print(f"High-confidence disagreements: {len(report['disagreements'])}")
    print(f"Review file: {out}")


if __name__ == "__main__":
    main()
