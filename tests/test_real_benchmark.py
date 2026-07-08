"""Unit tests for the real-world benchmark runner's math and manifest parsing.

The benchmark produces the numbers used in sales conversations — a metrics
bug here is worse than a detection bug, so the math gets its own tests.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.real_benchmark import compute_metrics, breakdown, method_breakdown, load_manifest


def _r(expected_ai, predicted_ai, **kw):
    return {"expected_ai": expected_ai, "predicted_ai": predicted_ai,
            "correct": expected_ai == predicted_ai, **kw}


def test_compute_metrics_perfect():
    results = [_r(True, True), _r(True, True), _r(False, False)]
    m = compute_metrics(results)
    assert m["accuracy"] == 1.0
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["fpr"] == 0.0
    assert m["confusion"] == {"tp": 2, "fp": 0, "fn": 0, "tn": 1}


def test_compute_metrics_known_confusion():
    # 3 AI (2 caught), 4 real (1 false positive)
    results = ([_r(True, True)] * 2 + [_r(True, False)] +
               [_r(False, False)] * 3 + [_r(False, True)])
    m = compute_metrics(results)
    assert m["confusion"] == {"tp": 2, "fp": 1, "fn": 1, "tn": 3}
    assert m["recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["fpr"] == pytest.approx(1 / 4, abs=1e-4)
    assert m["accuracy"] == pytest.approx(5 / 7, abs=1e-4)


def test_compute_metrics_division_safety():
    # All real, none flagged → precision/recall undefined, must be None not crash
    m = compute_metrics([_r(False, False)] * 3)
    assert m["precision"] is None
    assert m["recall"] is None
    assert m["fpr"] == 0.0


def test_breakdown_groups_by_key():
    results = [_r(True, True, platform="tiktok"), _r(False, True, platform="tiktok"),
               _r(False, False, platform="youtube")]
    by = breakdown(results, "platform")
    assert set(by) == {"tiktok", "youtube"}
    assert by["tiktok"]["confusion"]["fp"] == 1
    assert by["youtube"]["accuracy"] == 1.0


def test_method_breakdown_accuracy():
    results = [_r(True, True, method="C2PA: signed"), _r(True, False, method="C2PA: signed"),
               _r(False, False, method="ensemble")]
    mb = method_breakdown(results)
    key = next(k for k in mb if k.startswith("C2PA"))
    assert mb[key]["n"] == 2 and mb[key]["correct"] == 1


def test_load_manifest_csv_and_validation():
    d = Path(tempfile.mkdtemp())
    csv_path = d / "m.csv"
    csv_path.write_text("filename,label,platform,category\na.mp4,AI,TikTok,kling\nb.mp4,real,,\n")
    rows = load_manifest(csv_path)
    assert rows[0] == {"filename": "a.mp4", "label": "ai", "platform": "tiktok", "category": "kling"}
    assert rows[1]["platform"] == "unknown"

    bad = d / "bad.csv"
    bad.write_text("filename,label\nc.mp4,maybe\n")
    with pytest.raises(SystemExit):
        load_manifest(bad)


def test_load_manifest_json():
    d = Path(tempfile.mkdtemp())
    j = d / "m.json"
    j.write_text(json.dumps([{"filename": "x.mp4", "label": "ai"}]))
    rows = load_manifest(j)
    assert rows[0]["label"] == "ai"
    assert rows[0]["category"] == "unknown"
