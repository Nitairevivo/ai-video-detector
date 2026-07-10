"""
ML classifier that learns from labeled video samples.
Uses the feature vector from feature_extractor.py.
Designed to improve as more labeled data is collected.
"""
import os
import json
import numpy as np
import joblib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_predict


MODEL_PATH = Path(__file__).parent / "trained_model.joblib"
MODEL_META_PATH = Path(__file__).parent / "trained_model_meta.json"
TRAINING_DATA_PATH = Path(__file__).parent.parent / "data" / "training_samples.json"
# Real videos the user supplied (their own phone footage). Permanent ground-truth
# REAL samples merged into every retrain — they survive the nightly machine's
# restore-from-branch step (which only overwrites TRAINING_DATA_PATH).
USER_SEED_PATH = Path(__file__).parent.parent / "data" / "user_seed_videos.json"

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

    def _build_pipeline(self, n_samples: int = 0) -> Pipeline:
        base = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )
        # Probability calibration matters here more than in a typical classifier:
        # the ensemble fuses this probability with other layers in log-odds
        # space, so a miscalibrated 0.9 (that really means 0.6) skews the whole
        # fusion. Isotonic is more expressive but overfits on small data —
        # use sigmoid below ~400 samples.
        method = "isotonic" if n_samples >= 400 else "sigmoid"
        return Pipeline([
            ('scaler', StandardScaler()),
            ('clf', CalibratedClassifierCV(base, method=method, cv=5)),
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

        # Always fold in the user's own real footage (dedup by source).
        if USER_SEED_PATH.exists():
            try:
                seen = {s.get("source") for s in samples}
                for s in json.load(open(USER_SEED_PATH)):
                    if s.get("source") not in seen:
                        samples.append(s)
                        seen.add(s.get("source"))
            except Exception:
                pass

        if len(samples) < 20:
            return {"error": f"Need at least 20 samples, have {len(samples)}"}

        X = np.array([s["features"] for s in samples])
        y = np.array([s["label"] for s in samples])

        n_ai = int(y.sum())
        n_real = len(y) - n_ai
        if n_ai < 5 or n_real < 5:
            return {"error": f"Need at least 5 samples of each class. AI: {n_ai}, Real: {n_real}"}

        self.pipeline = self._build_pipeline(len(samples))

        # Honest evaluation BEFORE fitting on everything: out-of-fold predicted
        # probabilities for every sample, from which we derive all metrics an
        # enterprise buyer asks about — not just AUC.
        cv = StratifiedKFold(n_splits=min(5, len(samples) // 4), shuffle=True, random_state=42)
        oof_prob = cross_val_predict(self.pipeline, X, y, cv=cv, method="predict_proba")[:, 1]

        fold_aucs = [
            roc_auc_score(y[test_idx], oof_prob[test_idx])
            for _, test_idx in cv.split(X, y)
        ]
        oof_pred = oof_prob >= 0.5
        tp = int(((oof_pred == 1) & (y == 1)).sum())
        fp = int(((oof_pred == 1) & (y == 0)).sum())
        fn = int(((oof_pred == 0) & (y == 1)).sum())
        tn = int(((oof_pred == 0) & (y == 0)).sum())

        # Lowest threshold that keeps false positives on real videos <= 5%
        # (reported for callers that want a stricter operating point; predict()
        # itself stays at 0.5).
        real_probs = np.sort(oof_prob[y == 0])
        k = max(0, int(np.ceil(len(real_probs) * 0.95)) - 1)
        threshold_fpr5 = float(real_probs[k]) if len(real_probs) else 0.5

        self.pipeline.fit(X, y)
        joblib.dump(self.pipeline, MODEL_PATH)

        meta = {
            "samples": len(samples),
            "ai_samples": n_ai,
            "real_samples": n_real,
            "cv_auc_mean": float(np.mean(fold_aucs)),
            "cv_auc_std": float(np.std(fold_aucs)),
            "cv_brier": float(brier_score_loss(y, oof_prob)),
            "cv_accuracy": (tp + tn) / len(y),
            "cv_precision": tp / (tp + fp) if (tp + fp) else None,
            "cv_recall": tp / (tp + fn) if (tp + fn) else None,
            "cv_fpr": fp / (fp + tn) if (fp + tn) else None,
            "threshold_fpr5": threshold_fpr5,
            "calibration": "isotonic" if len(samples) >= 400 else "sigmoid",
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sklearn_version": sklearn.__version__,
        }
        MODEL_META_PATH.write_text(json.dumps(meta))
        self.is_trained = self._passes_quality_gate()

        quality_ok = self.is_trained
        return {
            "samples_used": len(samples),
            "ai_samples": n_ai,
            "real_samples": n_real,
            **{k: meta[k] for k in ("cv_auc_mean", "cv_auc_std", "cv_brier", "cv_accuracy",
                                    "cv_precision", "cv_recall", "cv_fpr", "threshold_fpr5")},
            "model_saved": str(MODEL_PATH),
            "model_active": quality_ok,
            "quality_gate": f"need {MIN_SAMPLES} samples / AUC {MIN_CV_AUC} — {'PASSED' if quality_ok else 'FAILED'}",
        }

    def feature_importance(self) -> Optional[dict]:
        if not self.is_trained:
            return None
        clf = self.pipeline.named_steps['clf']
        if isinstance(clf, CalibratedClassifierCV):
            # Average the underlying GB importances across calibration folds
            importances_list = [
                cc.estimator.feature_importances_
                for cc in clf.calibrated_classifiers_
                if hasattr(cc.estimator, "feature_importances_")
            ]
            if not importances_list:
                return None
            clf = type("_Avg", (), {"feature_importances_": np.mean(importances_list, axis=0)})()
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
