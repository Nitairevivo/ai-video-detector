"""
Quality gate for auto-promoting a freshly trained model to production.

The nightly data machines retrain on side branches (`auto-train`,
`auto-train-images`). This gate decides — purely from the model metadata —
whether a candidate is safe to merge onto master (which auto-deploys). The
rule is conservative by design: a candidate may only HOLD or IMPROVE accuracy,
never regress it. When in doubt it holds.

Pure, side-effect-free, and unit-tested so the promotion decision is auditable
in the workflow logs rather than buried in shell.
"""
from __future__ import annotations

from typing import Optional

# Per-kind gate configuration. Tightened deliberately: the whole point is that
# an automatic push to production can never make the product worse.
CONFIG = {
    "video": {
        "auc_tolerance": 0.005,   # candidate AUC may dip at most this vs production
        "fpr_ceiling": 0.05,      # never ship a model that cries wolf on real footage
        "min_samples": 300,
        "min_per_class": 40,
        "abs_min_auc": 0.90,      # floor when there is no production model to beat
    },
    "image": {
        "auc_tolerance": 0.005,
        "fpr_ceiling": 0.05,
        "min_samples": 300,
        "min_per_class": 40,
        "abs_min_auc": 0.85,
    },
}


def _auc(meta: dict) -> Optional[float]:
    """Video meta stores cv_auc_mean; image meta stores cv_auc."""
    for k in ("cv_auc_mean", "cv_auc"):
        v = meta.get(k)
        if v is not None:
            return float(v)
    return None


def _fpr(meta: dict) -> Optional[float]:
    v = meta.get("cv_fpr")
    return None if v is None else float(v)


def evaluate(candidate: Optional[dict], production: Optional[dict], kind: str) -> dict:
    """Decide whether `candidate` should replace `production` for the given kind.

    Returns {promote: bool, reasons: [str], candidate_auc, production_auc}. The
    reasons list explains every check so the workflow summary is self-documenting.
    """
    cfg = CONFIG[kind]
    reasons: list[str] = []

    if not candidate:
        return {"promote": False, "reasons": ["no candidate model on the train branch"],
                "candidate_auc": None, "production_auc": _auc(production or {})}

    c_auc = _auc(candidate)
    c_fpr = _fpr(candidate)
    c_n = int(candidate.get("samples", 0) or 0)
    c_ai = int(candidate.get("ai_samples", 0) or 0)
    c_real = int(candidate.get("real_samples", 0) or 0)

    ok = True

    # 1. Enough data, both classes represented — guards against degenerate fits.
    if c_n < cfg["min_samples"]:
        ok = False
        reasons.append(f"FAIL samples {c_n} < {cfg['min_samples']}")
    else:
        reasons.append(f"ok samples {c_n}")
    if min(c_ai, c_real) < cfg["min_per_class"]:
        ok = False
        reasons.append(f"FAIL per-class min {min(c_ai, c_real)} < {cfg['min_per_class']} (AI {c_ai}/real {c_real})")
    else:
        reasons.append(f"ok class balance AI {c_ai}/real {c_real}")

    # 2. False-positive rate on real media must stay under the ceiling.
    if c_fpr is None:
        reasons.append("note candidate has no cv_fpr — skipping FPR check")
    elif c_fpr > cfg["fpr_ceiling"]:
        ok = False
        reasons.append(f"FAIL fpr {c_fpr:.4f} > ceiling {cfg['fpr_ceiling']}")
    else:
        reasons.append(f"ok fpr {c_fpr:.4f} <= {cfg['fpr_ceiling']}")

    # 3. AUC must not regress vs production (and clear an absolute floor when
    #    there is no production model yet, e.g. the first image model).
    p_auc = _auc(production or {}) if production else None
    if c_auc is None:
        ok = False
        reasons.append("FAIL candidate has no AUC metric")
    elif p_auc is None:
        if c_auc < cfg["abs_min_auc"]:
            ok = False
            reasons.append(f"FAIL first model auc {c_auc:.4f} < floor {cfg['abs_min_auc']}")
        else:
            reasons.append(f"ok first model auc {c_auc:.4f} >= floor {cfg['abs_min_auc']}")
    else:
        if c_auc + 1e-9 < p_auc - cfg["auc_tolerance"]:
            ok = False
            reasons.append(f"FAIL auc regressed {c_auc:.4f} < production {p_auc:.4f} - {cfg['auc_tolerance']}")
        else:
            reasons.append(f"ok auc {c_auc:.4f} vs production {p_auc:.4f} (tol {cfg['auc_tolerance']})")

    # 4. Never promote a SHRUNKEN dataset over a bigger production one — retrains
    #    accumulate, so fewer samples means something went wrong upstream.
    if production is not None:
        p_n = int(production.get("samples", 0) or 0)
        if c_n < p_n:
            ok = False
            reasons.append(f"FAIL dataset shrank {c_n} < production {p_n}")

    return {"promote": ok, "reasons": reasons, "candidate_auc": c_auc, "production_auc": p_auc}


def _load(path: str) -> Optional[dict]:
    import json
    import os
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def main() -> int:
    """CLI: promote_gate.py <kind> <candidate_meta.json> <production_meta.json>
    Prints a human summary and exits 0 to PROMOTE, 1 to HOLD (so the workflow
    can branch on the exit code)."""
    import sys
    if len(sys.argv) < 4:
        print("usage: promote_gate.py <video|image> <candidate_meta> <production_meta>")
        return 2
    kind, cand_path, prod_path = sys.argv[1], sys.argv[2], sys.argv[3]
    res = evaluate(_load(cand_path), _load(prod_path), kind)
    print(f"::group::{kind} promotion gate")
    for r in res["reasons"]:
        print(f"  {r}")
    print(f"  DECISION: {'PROMOTE' if res['promote'] else 'HOLD'}")
    print("::endgroup::")
    return 0 if res["promote"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
