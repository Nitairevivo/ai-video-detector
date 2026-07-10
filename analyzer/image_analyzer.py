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
    from PIL import Image, ExifTags
    _PIL = True
except Exception:
    _PIL = False

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
        if needle.encode() in low:
            found["ai_tool"] = tool
            break
    return found


def _tool_from_text(exif: dict) -> Optional[str]:
    hay = " ".join(str(v).lower() for k, v in exif.items()
                   if k in ("software", "artist", "hostcomputer", "imagedescription")
                   or k.startswith("text::"))
    # Stable Diffusion's signature PNG chunk: a "parameters" field with a prompt
    if "text::parameters" in exif and ("steps:" in hay or "sampler" in hay or "cfg scale" in hay):
        return "Stable Diffusion"
    for needle, tool in AI_IMAGE_TOOLS.items():
        if needle in hay:
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
        # Stripped (screenshot / re-saved / platform) — no code evidence either
        # way. Report low confidence rather than guessing (mirrors the video path).
        return ImageResult("uncertain", 0.35, "No metadata — stripped image, no provenance to read", None, signals)
    return ImageResult("uncertain", 0.30, "Metadata present but no AI or camera markers", None, signals)
