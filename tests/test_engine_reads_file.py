"""Lab: prove the engine actually READS a real video file's code and turns it
into a verdict — the exact pipeline /detect runs on an uploaded WhatsApp/Telegram
file. Runs offline (no Gemini/network): it exercises the code-reading layer
(container/codec/metadata → signals + feature vector), the ML layer, and the
ensemble fusion. This is the closest offline proof of "reads the code behind
the video".
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import extract_features
from analyzer.ensemble import analyze_ensemble
from models.classifier import get_classifier

CANARY = str(Path(__file__).parent / "assets" / "canary.mp4")


def test_engine_reads_real_file_and_produces_verdict():
    assert os.path.exists(CANARY), "real test video is missing"

    # 1) Read the code behind the video: container/codec/metadata → signals+vector.
    result = extract_features(CANARY, deep=True)
    assert result is not None
    assert isinstance(result.feature_vector, list) and len(result.feature_vector) > 0
    assert isinstance(result.signals, dict) and len(result.signals) > 0
    assert 0.0 <= float(result.confidence) <= 1.0
    assert result.verdict in ("ai_generated", "ai_edited", "real")

    # 2) ML layer runs on the REAL feature vector without throwing.
    clf = get_classifier()
    ml_prob, _ = clf.predict(result.feature_vector)
    assert ml_prob is None or (0.0 <= float(ml_prob) <= 1.0)

    # 3) Ensemble fuses it into a final, structured verdict (offline, no Gemini).
    ens = analyze_ensemble(CANARY, result, ml_prob, use_gemini=False, gemini_result=None)
    assert ens.verdict in ("ai_generated", "ai_edited", "real", "unknown")
    assert 0.0 <= float(ens.confidence) <= 1.0
    assert isinstance(ens.method, str) and ens.method
    assert isinstance(ens.layers, dict)


def test_code_first_fast_path_reads_provenance():
    # The provenance/"code-first" fast path (used for C2PA / AI-tool tags) must
    # run on the real file and return a usable result.
    result = extract_features(CANARY, code_only=True)
    assert result is not None
    assert result.verdict in ("ai_generated", "ai_edited", "real")
    assert isinstance(result.signals, dict)
