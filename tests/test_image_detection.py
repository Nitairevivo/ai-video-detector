"""
Tests for the code-first AI *image* detector (analyzer.image_analyzer +
/detect image routing). Mirrors the video engine's guarantees: definitive on
provenance, and no false positives on real (camera-EXIF) photos.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

PIL = pytest.importorskip("PIL")
from PIL import Image, ExifTags               # noqa: E402
from PIL.PngImagePlugin import PngInfo        # noqa: E402

_TAG = {v: k for k, v in ExifTags.TAGS.items()}


def _img(color=(120, 140, 160)):
    return Image.new("RGB", (64, 48), color)


@pytest.fixture
def camera_photo(tmp_path):
    p = tmp_path / "cam.jpg"
    im = _img(); ex = im.getexif()
    ex[_TAG["Make"]] = "Apple"; ex[_TAG["Model"]] = "iPhone 15 Pro"
    ex[_TAG["DateTimeOriginal"]] = "2026:05:01 10:00:00"
    im.save(p, exif=ex)
    return str(p)


@pytest.fixture
def firefly_image(tmp_path):
    p = tmp_path / "firefly.jpg"
    im = _img(); ex = im.getexif(); ex[_TAG["Software"]] = "Adobe Firefly"
    im.save(p, exif=ex)
    return str(p)


@pytest.fixture
def sd_image(tmp_path):
    p = tmp_path / "sd.png"
    im = _img(); meta = PngInfo()
    meta.add_text("parameters", "a cat, masterpiece\nSteps: 30, Sampler: Euler a, CFG scale: 7, Model: sdxl")
    im.save(p, pnginfo=meta)
    return str(p)


@pytest.fixture
def iptc_image(tmp_path):
    p = tmp_path / "iptc.jpg"
    im = _img(); ex = im.getexif()
    ex[_TAG["ImageDescription"]] = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
    im.save(p, exif=ex)
    return str(p)


@pytest.fixture
def plain_image(tmp_path):
    p = tmp_path / "plain.png"
    _img().save(p)
    return str(p)


def test_camera_photo_is_real(camera_photo):
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(camera_photo)
    assert r.verdict == "real"
    assert r.confidence <= 0.2
    assert r.signals["camera_origin_detected"]


def test_firefly_is_ai(firefly_image):
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(firefly_image)
    assert r.verdict == "ai_generated"
    assert r.confidence >= 0.9
    assert r.ai_tool == "Adobe Firefly"


def test_stable_diffusion_png_is_ai(sd_image):
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(sd_image)
    assert r.verdict == "ai_generated"
    assert "Stable Diffusion" in (r.ai_tool or "")


def test_iptc_marker_is_ai(iptc_image):
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(iptc_image)
    assert r.verdict == "ai_generated"
    assert r.signals["synthetic_media_marker"]


def test_plain_image_not_falsely_flagged(plain_image):
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(plain_image)
    assert r.verdict != "ai_generated"   # never cry wolf without evidence


def test_tool_token_in_compressed_bytes_not_flagged(tmp_path):
    """Regression: a real photo whose *compressed* bytes coincidentally contain
    a short tool token (e.g. 'reve') must NOT be flagged AI. The tool tag only
    counts inside readable metadata, not random binary. (Found on a real
    user-supplied scan that JPEG-compressed into bytes spelling 'RevE'.)"""
    from analyzer.image_analyzer import _byte_scan
    p = tmp_path / "coincidence.jpg"
    payload = b"\xff\xd8\xff\xe0" + b"\x84\x04\x1a\x15\x96IZeT\x00RevE\xc9\x85\x89!\xa2" * 4
    p.write_bytes(payload)
    assert _byte_scan(str(p))["ai_tool"] is None


def test_tool_token_in_metadata_still_detected(tmp_path):
    """The guard must not blind us to a genuine tool tag sitting in real
    printable metadata text."""
    from analyzer.image_analyzer import _byte_scan
    p = tmp_path / "real_tag.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"tEXtSoftware\x00Created with Midjourney v6\x00")
    assert _byte_scan(str(p))["ai_tool"] == "Midjourney"


def test_image_feature_vector_shape(plain_image):
    from analyzer.image_analyzer import image_feature_vector, _IMG_FEATURE_KEYS
    v = image_feature_vector(plain_image)
    assert len(v) == len(_IMG_FEATURE_KEYS)
    assert all(isinstance(x, float) for x in v)


def test_image_model_trains_and_serves(tmp_path, plain_image, monkeypatch):
    """The image data machine trains a pixel model that analyze_image then uses
    for a stripped image (no metadata)."""
    import json, random
    import training.collect_images as ci
    from analyzer.image_analyzer import _IMG_FEATURE_KEYS
    ci.DATA = tmp_path / "img_samples.json"
    ci.MODEL = tmp_path / "image_model.joblib"
    ci.META = tmp_path / "image_meta.json"
    random.seed(0)
    n = len(_IMG_FEATURE_KEYS)
    samples = []
    ni = _IMG_FEATURE_KEYS.index("gray_noise")
    for i in range(40):
        ai = i % 2 == 0
        vec = [0.0] * n
        vec[ni] = (0.5 if ai else 3.0) + random.random()
        samples.append({"features": vec, "label": int(ai), "source": f"s{i}"})
    json.dump(samples, open(ci.DATA, "w"))
    meta = ci.train_image_model()
    assert meta.get("cv_auc", 0) >= 0.9
    assert ci.MODEL.exists()

    import analyzer.image_analyzer as ia
    monkeypatch.setattr(ia, "_IMG_MODEL_PATH", str(ci.MODEL))
    monkeypatch.setattr(ia, "_img_model", None)
    monkeypatch.setattr(ia, "_img_model_loaded", False)
    r = ia.analyze_image(plain_image)  # stripped image → model gives a verdict
    assert "pixel_model_prob" in r.signals


def test_detect_endpoint_routes_images(firefly_image):
    """/detect accepts an image and returns the image payload shape."""
    from api.server import run_image_analysis
    res = run_image_analysis(firefly_image)
    assert res["media_type"] == "image"
    assert res["verdict"] == "ai_generated"
    assert res["explanation"]["provenance"]["ai_tool"] == "Adobe Firefly"
