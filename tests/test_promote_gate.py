"""
Tests for the auto-promote quality gate (training.promote_gate). The gate is
what lets a nightly-trained model ship to production automatically, so its
"never regress" guarantee has to be pinned down.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from training.promote_gate import evaluate  # noqa: E402


def _video(auc, fpr=0.02, samples=1005, ai=400, real=605):
    return {"cv_auc_mean": auc, "cv_fpr": fpr, "samples": samples,
            "ai_samples": ai, "real_samples": real}


def _image(auc, fpr=0.02, samples=680, ai=270, real=410):
    return {"cv_auc": auc, "cv_fpr": fpr, "samples": samples,
            "ai_samples": ai, "real_samples": real}


def test_promotes_clear_improvement():
    prod = _video(0.955, samples=220, ai=150, real=70)
    cand = _video(0.982, fpr=0.013)
    res = evaluate(cand, prod, "video")
    assert res["promote"] is True


def test_holds_auc_regression():
    prod = _video(0.982, samples=1005)
    cand = _video(0.90, samples=1010)   # AUC dropped well past tolerance
    res = evaluate(cand, prod, "video")
    assert res["promote"] is False
    assert any("auc regressed" in r for r in res["reasons"])


def test_holds_high_fpr_even_if_auc_ok():
    prod = _video(0.955, samples=220, ai=150, real=70)
    cand = _video(0.98, fpr=0.12)       # cries wolf on real footage
    res = evaluate(cand, prod, "video")
    assert res["promote"] is False
    assert any("fpr" in r for r in res["reasons"])


def test_holds_dataset_shrink():
    prod = _video(0.982, samples=1005)
    cand = _video(0.99, samples=500)    # fewer samples than production -> suspect
    res = evaluate(cand, prod, "video")
    assert res["promote"] is False
    assert any("shrank" in r for r in res["reasons"])


def test_holds_too_few_samples():
    res = evaluate(_video(0.99, samples=50, ai=25, real=25), None, "video")
    assert res["promote"] is False


def test_holds_single_class():
    res = evaluate(_video(0.99, ai=1000, real=5), None, "video")
    assert res["promote"] is False
    assert any("per-class" in r for r in res["reasons"])


def test_first_image_model_promotes_over_absent_production():
    # No production image model on master yet — first model ships if it clears
    # the absolute floor.
    res = evaluate(_image(0.95), None, "image")
    assert res["promote"] is True


def test_first_model_below_floor_is_held():
    res = evaluate(_image(0.70), None, "image")
    assert res["promote"] is False


def test_no_candidate_holds():
    res = evaluate(None, _video(0.955), "video")
    assert res["promote"] is False
