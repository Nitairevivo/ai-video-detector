"""
Build/train the frame-level ML model.
Called at server startup if model is missing or corrupt.
Uses only synthetic data — no external downloads required.
"""
import subprocess
import tempfile
import os
import pickle
import numpy as np

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    SKLEARN = True
except ImportError:
    SKLEARN = False

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "frame_model.pkl")


def _make_video(vf: str, dur: int = 5, noise_audio: bool = False) -> str:
    tmp = tempfile.mktemp(suffix=".mp4")
    audio = "aevalsrc=random(0)*0.25:s=44100" if noise_audio else "sine=f=440"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size=480x270:rate=24",
         "-f", "lavfi", "-i", audio, "-t", str(dur), "-vf", vf,
         "-c:v", "libx264", "-crf", "22", "-c:a", "aac", tmp, "-loglevel", "error"],
        capture_output=True, timeout=25,
    )
    return tmp if r.returncode == 0 and os.path.exists(tmp) else None


def _reencode(src: str) -> str:
    dst = tempfile.mktemp(suffix=".mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-c:v", "libx264", "-crf", "28",
         "-preset", "fast", dst, "-loglevel", "error"],
        capture_output=True, timeout=15,
    )
    return dst if os.path.exists(dst) else src


def _extract(path: str):
    """Extract visual features from video. Must return 14 features to match detect_visual()."""
    try:
        from analyzer.frame_analyzer import (
            _get_frames, _local_block_variance, _inter_frame_diff,
            _fft_high_ratio, _temporal_consistency,
        )
        frames = _get_frames(path, n=16, size="128x72")
        if frames is None or len(frames) < 4:
            return None
        local_var = _local_block_variance(frames)
        ifd_mean, ifd_std = _inter_frame_diff(frames)
        fft_ratio = _fft_high_ratio(frames)
        temp_cv = _temporal_consistency(frames)
        diffs = [float(np.abs(frames[i+1]-frames[i]).mean()) for i in range(len(frames)-1)]
        ifd_p10 = float(np.percentile(diffs, 10)) if diffs else 0
        ifd_p90 = float(np.percentile(diffs, 90)) if diffs else 0
        ifd_range = ifd_p90 - ifd_p10
        means = [float(f.mean()) for f in frames]
        brightness_std = float(np.std(means))
        bv = []
        for f in frames[:8]:
            h, w = f.shape
            for r in range(0, h-4, 4):
                for c in range(0, w-4, 4):
                    bv.append(float(f[r:r+4, c:c+4].var()))
        lv_p5 = float(np.percentile(bv, 5)) if bv else 0
        lv_p50 = float(np.percentile(bv, 50)) if bv else 0
        lv_p95 = float(np.percentile(bv, 95)) if bv else 0
        # Motion features (synthetic videos have minimal motion — use 0.0 as placeholder)
        # This keeps the feature vector at 14 dimensions, matching detect_visual() at inference.
        try:
            from analyzer.motion_analyzer import analyze_motion
            mot = analyze_motion(path)
            motion_std = mot.signals.get("motion_std", 0.0)
            motion_cv = mot.signals.get("motion_temporal_cv", 0.0)
        except Exception:
            motion_std = motion_cv = 0.0
        return [local_var, ifd_mean, ifd_std, ifd_range, ifd_p10, ifd_p90,
                fft_ratio, temp_cv, brightness_std, lv_p5, lv_p50, lv_p95,
                motion_std, motion_cv]
    except Exception:
        return None


AI_FILTERS = [
    ("gblur=sigma=2.0", False),
    ("gblur=sigma=1.5,eq=saturation=1.2", False),
    ("gblur=sigma=2.5", False),
    ("gblur=sigma=1.0,unsharp=2:2:0.5", False),
    ("tmix=frames=5,gblur=sigma=1.0", False),
    ("tmix=frames=4,unsharp=2:2:0.4", False),
    ("unsharp=7:7:1.5", False),
    ("unsharp=5:5:1.2,gblur=sigma=0.2", False),
    ("gblur=sigma=2.0", True),   # TikTok re-encoded
    ("tmix=frames=4", True),
    ("unsharp=7:7:1.5", True),
    ("gblur=sigma=1.8,eq=saturation=1.1", False),
    ("gblur=sigma=0.8,eq=brightness=0.05", False),
    ("tmix=frames=3,gblur=sigma=1.5", False),
    ("gblur=sigma=3.0", False),
]

REAL_FILTERS = [
    ("noise=alls=22:allf=t", False, True),
    ("noise=alls=15:allf=t", False, True),
    ("noise=alls=35:allf=t,eq=brightness=-0.1", False, True),
    ("noise=alls=25:allf=t", False, True),
    ("noise=alls=18:allf=t", False, True),
    ("noise=alls=40:allf=t,eq=brightness=-0.2", False, True),
    ("noise=alls=20:allf=t", True, True),   # TikTok re-encoded
    ("noise=alls=15:allf=t", True, True),
    ("noise=alls=25:allf=t", True, True),
    ("noise=alls=8:allf=t", False, True),
    ("noise=alls=30:allf=t", False, True),
    ("noise=alls=12:allf=t,eq=contrast=0.95", False, True),
    ("noise=alls=20:allf=t,hue=h=sin(t)*2", False, True),
    ("noise=alls=18:allf=t", False, True),
    ("noise=alls=22:allf=t,eq=saturation=0.95", False, True),
]


def build_model(verbose: bool = False) -> bool:
    """Build and save the frame ML model. Returns True on success."""
    if not SKLEARN:
        return False

    try:
        import numpy as np
    except ImportError:
        return False

    if verbose:
        print("[frame_model] Building visual AI detection model...")

    X, y = [], []

    for vf, tt in AI_FILTERS:
        src = _make_video(vf)
        if not src:
            continue
        path = _reencode(src) if tt else src
        feat = _extract(path)
        if feat:
            X.append(feat)
            y.append(1)
        for p in set([src, path]):
            try: os.unlink(p)
            except: pass

    for vf, tt, na in REAL_FILTERS:
        src = _make_video(vf, noise_audio=na)
        if not src:
            continue
        path = _reencode(src) if tt else src
        feat = _extract(path)
        if feat:
            X.append(feat)
            y.append(0)
        for p in set([src, path]):
            try: os.unlink(p)
            except: pass

    if len(X) < 10 or sum(y) < 3 or (len(y) - sum(y)) < 3:
        if verbose:
            print(f"[frame_model] Not enough data ({len(X)} samples)")
        return False

    X = np.array(X)
    y = np.array(y)

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_samples_split=3, min_samples_leaf=2, random_state=42,
        )),
    ])
    model.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    if verbose:
        acc = (model.predict(X) == y).mean()
        print(f"[frame_model] Trained: {len(X)} samples, accuracy={acc:.0%}")
        print(f"[frame_model] Saved to {MODEL_PATH}")

    return True


def ensure_model(verbose: bool = False) -> bool:
    """Load model if it exists, build it if not. Returns True if model is ready."""
    # Try loading existing
    try:
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, "rb") as f:
                pickle.load(f)
            return True
    except Exception:
        pass  # corrupt or incompatible — rebuild

    return build_model(verbose=verbose)


if __name__ == "__main__":
    build_model(verbose=True)
