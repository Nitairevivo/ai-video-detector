"""
Code-first AI *image* detection — the still-image counterpart to the video
engine. Images carry even more readable "code" than video:

  • EXIF        — real cameras write Make/Model/GPS/lens; AI images have none.
  • C2PA        — Content Credentials (Adobe Firefly, DALL·E 3, …) sign images.
  • IPTC        — DigitalSourceType (trainedAlgorithmicMedia) in XMP.
  • PNG text    — Stable Diffusion writes the full prompt + model into the file.
  • Tool tags   — "Adobe Firefly", "Midjourney", "DALL·E", "Flux", …

Everything here is read from the file bytes/metadata — no pixels required for a
verdict when provenance exists, so it is fast and, like the video path, avoids
false positives on real photos (camera EXIF caps the AI score).
"""
import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    from PIL import Image, ExifTags, ImageFilter
    _PIL = True
except Exception:
    _PIL = False

try:
    import numpy as np
    _NP = True
except Exception:
    _NP = False

import pickle

_IMG_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "image_model.joblib")
_img_model = None
_img_model_loaded = False


def _load_image_model():
    """The pixel classifier for STRIPPED images (no metadata). Optional — the
    code-first path handles everything else without it."""
    global _img_model, _img_model_loaded
    if _img_model_loaded:
        return _img_model
    _img_model_loaded = True
    try:
        import joblib
        if os.path.exists(_IMG_MODEL_PATH):
            _img_model = joblib.load(_IMG_MODEL_PATH)
    except Exception:
        _img_model = None
    return _img_model

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
              ".tif", ".tiff", ".heic", ".heif", ".avif"}

# Generator names (substring match, case-insensitive) → canonical tool.
AI_IMAGE_TOOLS = {
    "firefly": "Adobe Firefly", "adobe firefly": "Adobe Firefly",
    "dall-e": "DALL·E", "dall·e": "DALL·E", "dalle": "DALL·E",
    "midjourney": "Midjourney",
    "stable diffusion": "Stable Diffusion", "stable-diffusion": "Stable Diffusion",
    "stablediffusion": "Stable Diffusion", "sdxl": "Stable Diffusion",
    "automatic1111": "Stable Diffusion", "comfyui": "Stable Diffusion",
    "invokeai": "Stable Diffusion", "a1111": "Stable Diffusion",
    "flux": "Flux (Black Forest Labs)",
    "leonardo.ai": "Leonardo AI", "leonardo ai": "Leonardo AI",
    "ideogram": "Ideogram", "recraft": "Recraft",
    "playground": "Playground AI", "nightcafe": "NightCafe",
    "imagen": "Google Imagen", "gemini": "Google Gemini",
    "grok": "xAI Grok", "aurora": "xAI Aurora",
    "openai": "OpenAI", "gpt-image": "OpenAI GPT Image",
    "bing image creator": "Bing Image Creator", "designer.microsoft": "Microsoft Designer",
    "krea": "Krea", "reve": "Reve",
}

# IPTC DigitalSourceType leaves (shared with the video engine).
_IPTC_AI = (b"trainedAlgorithmicMedia", b"compositeWithTrainedAlgorithmicMedia",
            b"algorithmicMedia", b"compositeSynthetic")
_IPTC_CAPTURE = (b"digitalCapture", b"negativeFilm", b"positiveFilm")
_C2PA_UUID = b"\xd8\xfe\xc3\xd6\x1b\x0e\x48\x3c\x92\x97\x58\x28\x87\x7e\xc4\x81"

# Camera Make/Model hints that mark a real capture.
_CAMERA_MAKES = ("apple", "samsung", "google", "canon", "nikon", "sony",
                 "fujifilm", "panasonic", "olympus", "xiaomi", "huawei",
                 "oneplus", "motorola", "gopro", "dji", "leica", "pentax",
                 "oppo", "vivo", "realme", "nothing")


@dataclass
class ImageResult:
    verdict: str = "real"           # ai_generated | real | uncertain
    confidence: float = 0.0         # AI probability 0..1
    method: str = ""
    ai_tool: Optional[str] = None
    signals: dict = field(default_factory=dict)


def _read_exif(path: str) -> dict:
    """Return a flat dict of the interesting EXIF/text fields."""
    out = {}
    if not _PIL:
        return out
    try:
        with Image.open(path) as im:
            out["format"] = im.format
            out["mode"] = im.mode
            out["width"], out["height"] = im.size
            # PNG / WebP text chunks (Stable Diffusion writes here)
            for k, v in (getattr(im, "text", {}) or {}).items():
                out[f"text::{k.lower()}"] = str(v)
            exif = im.getexif()
            if exif:
                tagmap = {v: k for k, v in ExifTags.TAGS.items()}
                for name in ("Make", "Model", "Software", "Artist",
                             "DateTime", "DateTimeOriginal", "LensModel",
                             "HostComputer", "ImageDescription"):
                    tid = tagmap.get(name)
                    if tid and tid in exif:
                        out[name.lower()] = str(exif[tid]).strip()
                # GPS present at all → real-world capture
                gps_tid = tagmap.get("GPSInfo")
                if gps_tid and exif.get(gps_tid):
                    out["gps"] = True
    except Exception:
        pass
    return out


def _byte_scan(path: str) -> dict:
    """Scan the file head for provenance markers (works on any container)."""
    found = {"has_c2pa": False, "iptc_ai": None, "iptc_capture": False, "ai_tool": None}
    try:
        with open(path, "rb") as f:
            blob = f.read(3 * 1024 * 1024)  # 3 MB is plenty for image metadata
    except Exception:
        return found
    if _C2PA_UUID in blob or b"c2pa" in blob:
        found["has_c2pa"] = True
    for tok in _IPTC_AI:
        if tok in blob:
            found["iptc_ai"] = tok.decode()
            break
    for tok in _IPTC_CAPTURE:
        if tok in blob:
            found["iptc_capture"] = True
            break
    low = blob.lower()
    for needle, tool in AI_IMAGE_TOOLS.items():
        nb = needle.encode()
        start = 0
        while True:
            idx = low.find(nb, start)
            if idx < 0:
                break
            # A genuine tool tag lives in readable metadata text; a random
            # collision inside compressed pixel bytes does not. Require both a
            # printable-ASCII neighbourhood AND a whole-token boundary (so a
            # short token like "flux"/"reve" can't match inside a real word).
            if _in_text_region(blob, idx, len(nb)) and _byte_token_boundary(blob, idx, len(nb)):
                found["ai_tool"] = tool
                break
            start = idx + 1
        if found["ai_tool"]:
            break
    return found


def _in_text_region(blob: bytes, idx: int, length: int, pad: int = 6,
                    min_ratio: float = 0.85) -> bool:
    """True if the bytes around [idx, idx+length) are mostly printable ASCII.

    Tool names in EXIF/XMP/PNG-text are surrounded by readable characters; a
    chance match of a short token like "reve" or "flux" inside a JPEG's
    compressed data is surrounded by non-printable bytes. This keeps a real
    photo from being flagged AI just because its pixel bytes spell a tool name.
    """
    a = max(0, idx - pad)
    b = min(len(blob), idx + length + pad)
    window = blob[a:b]
    if not window:
        return False
    printable = sum(1 for c in window if 32 <= c <= 126)
    return printable / len(window) >= min_ratio


def _byte_token_boundary(blob: bytes, idx: int, length: int) -> bool:
    """The matched token must not be flanked by ASCII letters/digits, so a short
    token like "flux"/"reve" doesn't match inside "influx"/"forever" in metadata
    text either."""
    def _alnum(c: int) -> bool:
        return (48 <= c <= 57) or (65 <= c <= 90) or (97 <= c <= 122)
    before = blob[idx - 1] if idx > 0 else None
    after = blob[idx + length] if idx + length < len(blob) else None
    return not (before is not None and _alnum(before)) and not (after is not None and _alnum(after))


def _token_present(text: str, needle: str) -> bool:
    """Whole-token match: the needle must not be flanked by ASCII letters/digits.
    Stops short brand tokens from matching inside ordinary words — e.g. "flux"
    in "influx"/"reflux" or "reve" in "forever"/"reverie" — which would otherwise
    flag a real photo as AI from a caption. Punctuation/spaces still delimit, so
    "Adobe Firefly", "DALL·E 3" and "sdxl_model" match as intended."""
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text) is not None


def _tool_from_text(exif: dict) -> Optional[str]:
    hay = " ".join(str(v).lower() for k, v in exif.items()
                   if k in ("software", "artist", "hostcomputer", "imagedescription")
                   or k.startswith("text::"))
    # Stable Diffusion's signature PNG chunk: a "parameters" field with a prompt
    if "text::parameters" in exif and ("steps:" in hay or "sampler" in hay or "cfg scale" in hay):
        return "Stable Diffusion"
    for needle, tool in AI_IMAGE_TOOLS.items():
        if _token_present(hay, needle):
            return tool
    return None


def _has_camera_origin(exif: dict) -> bool:
    make = (exif.get("make") or "").lower()
    model = exif.get("model") or ""
    if exif.get("gps"):
        return True
    if make and any(m in make for m in _CAMERA_MAKES):
        return True
    if make and model and (exif.get("datetimeoriginal") or exif.get("datetime")):
        return True  # make+model+capture time is a strong camera signature
    return False


def _pixel_features(path: str) -> dict:
    """Cheap pixel statistics that separate camera photos from AI renders even
    when all metadata is gone (screenshots / re-saved / platform-stripped)."""
    f = {"gray_noise": 0.0, "edge_mean": 0.0, "fft_high_ratio": 0.0,
         "chan_std": 0.0, "sat_mean": 0.0}
    if not (_PIL and _NP):
        return f
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((256, 256))
            arr = np.asarray(im).astype("float32")
        gray = arr.mean(axis=2)
        # sensor-noise proxy: residual after a light blur (AI images are cleaner)
        with Image.fromarray(gray.astype("uint8")) as g:
            blur = np.asarray(g.filter(ImageFilter.GaussianBlur(2))).astype("float32")
        f["gray_noise"] = float(np.abs(gray - blur).mean())
        # edge energy
        gx = np.abs(np.diff(gray, axis=1)).mean()
        gy = np.abs(np.diff(gray, axis=0)).mean()
        f["edge_mean"] = float((gx + gy) / 2)
        # high-frequency spectral ratio
        F = np.abs(np.fft.fftshift(np.fft.fft2(gray)))
        h, w = F.shape
        cy, cx = h // 2, w // 2
        r = min(h, w) // 8
        low = F[cy - r:cy + r, cx - r:cx + r].sum()
        tot = F.sum() + 1e-6
        f["fft_high_ratio"] = float(1.0 - low / tot)
        # colour spread + saturation
        f["chan_std"] = float(arr.reshape(-1, 3).std(axis=0).mean())
        mx = arr.max(axis=2); mn = arr.min(axis=2)
        f["sat_mean"] = float(((mx - mn) / (mx + 1e-6)).mean())
    except Exception:
        pass
    return f


# Fixed-order numeric vector for the image ML model.
_IMG_FEATURE_KEYS = [
    "has_c2pa", "c2pa_is_ai", "synthetic_media_marker", "camera_provenance",
    "camera_origin_detected", "metadata_is_stripped",
    "has_make", "has_software", "has_png_text", "has_gps",
    "aspect", "megapixels",
    "gray_noise", "edge_mean", "fft_high_ratio", "chan_std", "sat_mean",
]

# The pixel model runs ONLY on stripped images (no metadata to read), so it must
# train and serve on the features that are actually present and meaningful then:
# the pixel statistics. Metadata flags are all-zero for a stripped image, and
# aspect/megapixels merely encode the source dataset's resolution — a spurious
# artifact that let a naive model score a hollow ~1.0 AUC while ignoring every
# real pixel signal. Restricting to these keys forces honest pixel evidence.
_PIXEL_MODEL_KEYS = ["gray_noise", "edge_mean", "fft_high_ratio", "chan_std", "sat_mean"]
_PIXEL_MODEL_IDX = [_IMG_FEATURE_KEYS.index(k) for k in _PIXEL_MODEL_KEYS]
# Operating threshold for the weak pixel heuristic — chosen so its false-positive
# rate stays low (~4%). Shared with training so reported metrics match real use.
_PIXEL_AI_THRESHOLD = 0.85


def pixel_model_vector(full_vec: list) -> list:
    """The pixel-only sub-vector the image model trains/serves on (see above)."""
    return [float(full_vec[i]) for i in _PIXEL_MODEL_IDX]


def image_feature_vector(path: str) -> list:
    """Numeric feature vector for training/serving the image model."""
    exif = _read_exif(path)
    scan = _byte_scan(path)
    px = _pixel_features(path)
    w = float(exif.get("width") or 0); h = float(exif.get("height") or 0)
    feats = {
        "has_c2pa": int(scan["has_c2pa"]),
        "c2pa_is_ai": 0,  # cryptographic flag only set in analyze_image; keep 0 here
        "synthetic_media_marker": int(bool(scan["iptc_ai"])),
        "camera_provenance": int(bool(scan["iptc_capture"])),
        "camera_origin_detected": int(_has_camera_origin(exif)),
        "metadata_is_stripped": int(not (exif.get("make") or exif.get("software") or any(k.startswith("text::") for k in exif))),
        "has_make": int(bool(exif.get("make"))),
        "has_software": int(bool(exif.get("software"))),
        "has_png_text": int(any(k.startswith("text::") for k in exif)),
        "has_gps": int(bool(exif.get("gps"))),
        "aspect": (w / h) if h else 0.0,
        "megapixels": (w * h) / 1e6,
        **px,
    }
    return [float(feats.get(k, 0.0)) for k in _IMG_FEATURE_KEYS]


def analyze_image(path: str) -> ImageResult:
    exif = _read_exif(path)
    scan = _byte_scan(path)

    # C2PA (cryptographic) via the shared verifier — works on images.
    c2pa_is_ai = False
    c2pa_present = scan["has_c2pa"]
    c2pa_gen = None
    try:
        from analyzer.c2pa_verifier import read_c2pa
        c = read_c2pa(path)
        if c.present:
            c2pa_present = True
            c2pa_is_ai = c.is_ai
            c2pa_gen = c.claim_generator
    except Exception:
        pass

    tool = _tool_from_text(exif) or scan["ai_tool"]
    camera = _has_camera_origin(exif)
    metadata_present = bool(
        exif.get("make") or exif.get("software") or exif.get("model")
        or any(k.startswith("text::") for k in exif) or c2pa_present
    )

    signals = {
        "has_c2pa": int(c2pa_present),
        "c2pa_is_ai": int(c2pa_is_ai),
        "synthetic_media_marker": int(bool(scan["iptc_ai"])),
        "iptc_digital_source_type": scan["iptc_ai"],
        "camera_provenance": int(bool(scan["iptc_capture"]) or camera),
        "ai_tool": tool,
        "camera_origin_detected": int(camera),
        "metadata_is_stripped": int(not metadata_present),
        "format": exif.get("format"),
        "width": exif.get("width"),
        "height": exif.get("height"),
    }

    # ── Rule cascade (most → least certain) ──────────────────────────────────
    if c2pa_is_ai:
        detail = "C2PA cryptographic proof of AI generation"
        if c2pa_gen:
            detail += f" (signed by {c2pa_gen})"
        return ImageResult("ai_generated", 0.99, detail, tool or (f"C2PA: {c2pa_gen}" if c2pa_gen else "C2PA"), signals)
    if tool:
        return ImageResult("ai_generated", 0.97, f"AI image tool in metadata: '{tool}'", tool, signals)
    if scan["iptc_ai"] and "composite" not in scan["iptc_ai"].lower():
        return ImageResult("ai_generated", 0.94, f"IPTC DigitalSourceType declares AI generation: '{scan['iptc_ai']}'", tool or f"IPTC:{scan['iptc_ai']}", signals)
    if scan["iptc_ai"]:
        return ImageResult("ai_generated", 0.80, f"IPTC DigitalSourceType declares partial AI: '{scan['iptc_ai']}'", tool, signals)
    if camera:
        return ImageResult("real", 0.05, "Camera EXIF markers — real photo", None, signals)
    if not metadata_present:
        # Stripped (screenshot / re-saved / platform) — no code evidence. Fall
        # back to the pixel model if it has been trained; otherwise stay honest.
        model = _load_image_model()
        if model is not None:
            try:
                prob = float(model.predict_proba([pixel_model_vector(image_feature_vector(path))])[0][1])
                signals["pixel_model_prob"] = round(prob, 3)
                # Pixel-only evidence on a stripped image is a WEAK heuristic
                # (honest CV: ~4% FPR only at a 0.85 cut), so act only at the
                # extremes and never claim provenance-level certainty — confidence
                # is capped. Bias against false positives: prefer uncertain.
                if prob >= _PIXEL_AI_THRESHOLD:
                    return ImageResult("ai_generated", min(prob, 0.72),
                                       f"Pixel heuristic (no metadata): looks AI-generated ({prob:.0%})", None, signals)
                if prob <= (1 - _PIXEL_AI_THRESHOLD):
                    return ImageResult("real", min(1 - prob, 0.72),
                                       f"Pixel heuristic (no metadata): looks real ({(1 - prob):.0%})", None, signals)
            except Exception:
                pass
        return ImageResult("uncertain", 0.35, "No metadata — stripped image, no provenance to read", None, signals)
    return ImageResult("uncertain", 0.30, "Metadata present but no AI or camera markers", None, signals)
