"""
ML classifier that learns from labeled video samples.
Uses the feature vector from feature_extractor.py.
Designed to improve as more labeled data is collected.
"""
import os
import json
import numpy as np
import joblib
from pathlib import Path
from typing import Optional
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score


MODEL_PATH = Path(__file__).parent / "trained_model.joblib"
MODEL_META_PATH = Path(__file__).parent / "trained_model_meta.json"
TRAINING_DATA_PATH = Path(__file__).parent.parent / "data" / "training_samples.json"

# Minimum quality requirements to use the ML model.
# Below these thresholds the model causes more false positives than it solves.
MIN_SAMPLES = 40          # minimum total labeled samples
MIN_CV_AUC = 0.70         # minimum cross-validation AUC
MIN_CLASS_SAMPLES = 15    # minimum samples per class (AI and real)


class VideoAIClassifier:
    def __init__(self):
        self.pipeline: Optional[Pipeline] = None
        self.is_trained = False
        self._load_if_exists()

    def _load_if_exists(self):
        if MODEL_PATH.exists():
            try:
                self.pipeline = joblib.load(MODEL_PATH)
                # Only mark as trained if it meets quality thresholds
                self.is_trained = self._passes_quality_gate()
            except Exception:
                self.pipeline = None
                self.is_trained = False

    def _passes_quality_gate(self) -> bool:
        if not MODEL_META_PATH.exists():
            return False
        try:
            meta = json.loads(MODEL_META_PATH.read_text())
            return (
                meta.get("samples", 0) >= MIN_SAMPLES and
                meta.get("cv_auc_mean", 0) >= MIN_CV_AUC and
                meta.get("ai_samples", 0) >= MIN_CLASS_SAMPLES and
                meta.get("real_samples", 0) >= MIN_CLASS_SAMPLES
            )
        except Exception:
            return False

    def _build_pipeline(self) -> Pipeline:
        return Pipeline([
            ('scaler', StandardScaler()),
            ('clf', GradientBoostingClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42,
            ))
        ])

    def predict(self, feature_vector: list) -> tuple[float, bool]:
        """
        Returns (ai_probability, is_ai).
        Falls back to rule-based score if model not trained.
        """
        if not self.is_trained or self.pipeline is None:
            return None, None

        x = np.array(feature_vector).reshape(1, -1)
        prob = float(self.pipeline.predict_proba(x)[0][1])
        return prob, prob >= 0.5

    def add_sample(self, feature_vector: list, label: bool, source: str = "manual"):
        """
        Adds a labeled sample to the training dataset.
        label=True means AI-generated, False means real.
        """
        TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

        samples = []
        if TRAINING_DATA_PATH.exists():
            with open(TRAINING_DATA_PATH) as f:
                samples = json.load(f)

        samples.append({
            "features": feature_vector,
            "label": int(label),
            "source": source,
        })

        with open(TRAINING_DATA_PATH, 'w') as f:
            json.dump(samples, f)

        print(f"Sample added. Total samples: {len(samples)}")

    def train(self) -> dict:
        """
        Trains the model on all collected samples.
        Needs at least 20 samples (10 AI, 10 real) to train.
        """
        if not TRAINING_DATA_PATH.exists():
            return {"error": "No training data found. Add samples first."}

        with open(TRAINING_DATA_PATH) as f:
            samples = json.load(f)

        if len(samples) < 20:
            return {"error": f"Need at least 20 samples, have {len(samples)}"}

        X = np.array([s["features"] for s in samples])
        y = np.array([s["label"] for s in samples])

        n_ai = int(y.sum())
        n_real = len(y) - n_ai
        if n_ai < 5 or n_real < 5:
            return {"error": f"Need at least 5 samples of each class. AI: {n_ai}, Real: {n_real}"}

        self.pipeline = self._build_pipeline()

        # Cross-validate before saving
        cv_scores = cross_val_score(self.pipeline, X, y, cv=min(5, len(samples) // 4), scoring='roc_auc')

        self.pipeline.fit(X, y)
        joblib.dump(self.pipeline, MODEL_PATH)

        meta = {
            "samples": len(samples),
            "ai_samples": n_ai,
            "real_samples": n_real,
            "cv_auc_mean": float(cv_scores.mean()),
            "cv_auc_std": float(cv_scores.std()),
        }
        MODEL_META_PATH.write_text(json.dumps(meta))
        self.is_trained = self._passes_quality_gate()

        quality_ok = self.is_trained
        return {
            "samples_used": len(samples),
            "ai_samples": n_ai,
            "real_samples": n_real,
            "cv_auc_mean": meta["cv_auc_mean"],
            "cv_auc_std": meta["cv_auc_std"],
            "model_saved": str(MODEL_PATH),
            "model_active": quality_ok,
            "quality_gate": f"need {MIN_SAMPLES} samples / AUC {MIN_CV_AUC} — {'PASSED' if quality_ok else 'FAILED'}",
        }

    def feature_importance(self) -> Optional[dict]:
        if not self.is_trained:
            return None
        clf = self.pipeline.named_steps['clf']
        feature_names = [
            # Metadata
            "has_ai_metadata_tag", "has_ai_exclusive_encoder", "has_c2pa",
            "c2pa_is_ai", "software_tag_present",
            # Codec
            "pts_uniformity", "pts_jitter_std",
            "keyframe_interval_std", "keyframe_interval_mean",
            "frame_size_cv", "frame_size_skewness",
            "codec_ai_score",
            "has_b_frames", "ref_frames",
            # Container
            "moov_before_mdat", "has_fragmented_mp4", "has_proprietary_box",
            "container_ai_score", "container_anomaly_score",
            "has_unknown_proprietary_boxes", "unknown_box_count",
            # Audio
            "has_audio", "is_fully_silent", "silence_ratio", "audio_rms_cv", "audio_ai_score",
            # Scene & entropy
            "scene_change_rate", "scene_change_uniformity",
            "entropy_mean", "entropy_std", "entropy_cv",
            # Stripped / platform
            "metadata_is_stripped", "platform_reencoded", "too_short_for_analysis",
            # Frequency domain
            "freq_hf_ratio", "freq_spectral_flatness", "freq_inter_frame_var",
            "freq_ai_score", "freq_analyzed",
            # Visual
            "visual_noise_floor", "visual_sharpness_cv", "visual_brightness_cv",
            "visual_ai_score", "visual_analyzed",
            # File
            "fps",
        ]
        importances = clf.feature_importances_
        n = min(len(feature_names), len(importances))
        return dict(sorted(
            zip(feature_names[:n], importances[:n]),
            key=lambda x: x[1], reverse=True
        ))


_classifier = VideoAIClassifier()


def get_classifier() -> VideoAIClassifier:
    return _classifier
