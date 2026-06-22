"""
FastAPI server — upload a video, get AI detection results in seconds.
"""
import os
import tempfile
import urllib.request
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from analyzer import extract_features
from models.classifier import get_classifier

app = FastAPI(
    title="AI Video Detector",
    description="Detects AI-generated videos by reading file signatures — no frame decoding required.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_FORMATS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB


@app.get("/")
def root():
    classifier = get_classifier()
    return {
        "status": "ok",
        "model_trained": classifier.is_trained,
        "supported_formats": list(SUPPORTED_FORMATS),
    }


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}. Use: {SUPPORTED_FORMATS}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(413, "File too large (max 2GB)")
        tmp.write(content)

    try:
        result = extract_features(tmp_path)
        classifier = get_classifier()
        ml_prob, ml_is_ai = classifier.predict(result.feature_vector)

        # Blend rule-based + ML if available
        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            method = f"ML+Rules ({result.method})"
        else:
            final_confidence = result.confidence
            method = result.method + " (rules only — train model for higher accuracy)"

        return {
            "filename": file.filename,
            "is_ai_generated": final_confidence >= 0.5,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "detection_method": method,
            "signals": result.signals,
            "rule_based_confidence": round(result.confidence, 4),
            "ml_confidence": round(ml_prob, 4) if ml_prob is not None else None,
        }
    finally:
        os.unlink(tmp_path)


@app.post("/label")
async def label_sample(file: UploadFile = File(...), is_ai: bool = True):
    """
    Submit a labeled video to improve the ML model.
    is_ai=true for AI-generated, false for real footage.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await file.read())

    try:
        result = extract_features(tmp_path)
        classifier = get_classifier()
        classifier.add_sample(result.feature_vector, label=is_ai, source=file.filename)
        return {"message": "Sample added to training set", "label": "AI" if is_ai else "Real"}
    finally:
        os.unlink(tmp_path)


@app.post("/train")
def train_model():
    """Train the ML model on all collected labeled samples."""
    classifier = get_classifier()
    result = classifier.train()
    return result


@app.post("/detect-url")
async def detect_url(url: str = Body(..., embed=True)):
    """
    Detect AI from a direct video URL (used by browser extension).
    Downloads only the first 2MB (headers + container) for fast analysis.
    """
    DOWNLOAD_LIMIT = 2 * 1024 * 1024  # 2MB is enough for metadata

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    suffix = ".mp4"
    for ext in [".mp4", ".mov", ".mkv", ".webm", ".m4v"]:
        if ext in url.lower():
            suffix = ext
            break

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                tmp.write(resp.read(DOWNLOAD_LIMIT))
        except Exception as e:
            os.unlink(tmp_path)
            raise HTTPException(400, f"Failed to download URL: {e}")

    try:
        result = extract_features(tmp_path)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)

        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            method = f"ML+Rules ({result.method})"
        else:
            final_confidence = result.confidence
            method = result.method

        return {
            "url": url,
            "is_ai_generated": final_confidence >= 0.5,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "detection_method": method,
        }
    finally:
        os.unlink(tmp_path)


@app.get("/model/importance")
def feature_importance():
    classifier = get_classifier()
    importance = classifier.feature_importance()
    if importance is None:
        return {"error": "Model not trained yet. POST /train first."}
    return {"feature_importance": importance}
