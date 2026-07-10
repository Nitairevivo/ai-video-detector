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


def test_detect_endpoint_routes_images(firefly_image):
    """/detect accepts an image and returns the image payload shape."""
    from api.server import run_image_analysis
    res = run_image_analysis(firefly_image)
    assert res["media_type"] == "image"
    assert res["verdict"] == "ai_generated"
    assert res["explanation"]["provenance"]["ai_tool"] == "Adobe Firefly"
