"""
Real C2PA (Content Credentials) verification.

Replaces the naive byte-scan (looking for the literal string ``c2pa.ai``) with
cryptographic manifest validation via the official ``c2pa`` library, and reads
the IPTC ``digitalSourceType`` to decide whether the credential actually claims
AI generation.

Why this matters: the old scan treated *any* file containing the bytes
``c2pa.ai`` as "cryptographic proof of AI" at 0.99 confidence. That string can
be embedded by anyone, so it was a false-positive vector. Here we only claim AI
when a *validly signed* manifest carries an AI ``digitalSourceType``.

The native library needs Python 3.10+ (production runs 3.11). When it can't be
imported, ``read_c2pa`` degrades gracefully to ``present=False`` and the caller
falls back to the presence-only byte scan. The manifest-interpretation logic
(:func:`interpret_manifest_store`) is pure and unit-tested independently of the
native library.
"""
from dataclasses import dataclass, field
from typing import Optional


# IPTC DigitalSourceType tokens (the URIs end with these). Ref:
# http://cv.iptc.org/newscodes/digitalsourcetype/
_AI_SOURCE_TOKENS = {
    "trainedalgorithmicmedia",             # fully GenAI
    "compositewithtrainedalgorithmicmedia",  # real + GenAI composite
    "algorithmicmedia",                     # algorithmically generated
}
_REAL_SOURCE_TOKENS = {
    "digitalcapture",      # camera original
    "negativefilm",
    "positivefilm",
    "print",
    "minorhumanedits",
    "compositecapture",
}

# Substrings in a C2PA validation_status code that indicate a *failed* check.
# Anything else (e.g. "*.validated", "*.trusted") is treated as passing.
_FAILURE_HINTS = (
    "mismatch", "invalid", "untrusted", "revoked", "missing",
    "notcredible", "malformed", "unsupported", "outofrange", "error",
)


@dataclass
class C2paResult:
    present: bool = False              # a manifest was found and parsed
    signature_valid: bool = False      # cryptographic validation passed
    is_ai: bool = False                # a valid manifest claims AI generation
    digital_source_type: Optional[str] = None
    claim_generator: Optional[str] = None
    validation_codes: list = field(default_factory=list)
    info: str = ""


def _source_token(uri: str) -> str:
    """Last path segment of a digitalSourceType URI, lowercased."""
    return (uri or "").rstrip("/").rsplit("/", 1)[-1].lower()


def _iter_actions(manifest: dict):
    """Yield every action dict across c2pa.actions / c2pa.actions.v2 assertions."""
    for assertion in manifest.get("assertions", []) or []:
        label = assertion.get("label", "")
        if not label.startswith("c2pa.actions"):
            continue
        data = assertion.get("data", {}) or {}
        for action in data.get("actions", []) or []:
            yield action


def _extract_digital_source_type(manifest: dict) -> Optional[str]:
    """
    Find a digitalSourceType for this asset. Prefer created/opened actions,
    but accept any action carrying the field.
    """
    fallback = None
    for action in _iter_actions(manifest):
        dst = action.get("digitalSourceType")
        if not dst:
            continue
        act = (action.get("action") or "").lower()
        if act in ("c2pa.created", "c2pa.opened"):
            return dst
        if fallback is None:
            fallback = dst
    return fallback


def _claim_generator(manifest: dict) -> Optional[str]:
    """Human-readable signer/tool name, across legacy and v2 manifest shapes."""
    info = manifest.get("claim_generator_info")
    if isinstance(info, list) and info and isinstance(info[0], dict):
        name = info[0].get("name")
        if name:
            return name
    return manifest.get("claim_generator")


def _collect_validation_codes(store: dict, manifest: dict) -> list:
    """
    Gather validation status codes from wherever the library placed them:
    top-level ``validation_status`` (legacy) or ``validation_results`` (newer),
    plus any on the active manifest itself.
    """
    codes: list = []

    def _pull(entries):
        for e in entries or []:
            if isinstance(e, dict) and e.get("code"):
                codes.append(e["code"])

    _pull(store.get("validation_status"))
    _pull(manifest.get("validation_status"))

    results = store.get("validation_results")
    if isinstance(results, dict):
        for bucket in results.values():
            if isinstance(bucket, dict):
                for entries in bucket.values():
                    _pull(entries)
    return codes


def _signature_is_valid(codes: list) -> bool:
    """Valid unless any code contains a known failure hint."""
    for code in codes:
        low = str(code).lower()
        if any(hint in low for hint in _FAILURE_HINTS):
            return False
    return True


def interpret_manifest_store(store: dict) -> C2paResult:
    """
    Pure interpretation of a parsed C2PA manifest store (the dict form of
    ``Reader.json()``). Unit-tested without the native library.
    """
    res = C2paResult(present=True)

    active_label = store.get("active_manifest")
    manifests = store.get("manifests", {}) or {}
    manifest = manifests.get(active_label) if active_label else None
    if manifest is None and manifests:
        # No active pointer — take any single manifest present.
        manifest = next(iter(manifests.values()))
    if manifest is None:
        res.present = False
        return res

    res.claim_generator = _claim_generator(manifest)

    res.validation_codes = _collect_validation_codes(store, manifest)
    res.signature_valid = _signature_is_valid(res.validation_codes)

    dst = _extract_digital_source_type(manifest)
    res.digital_source_type = dst
    token = _source_token(dst)

    if token in _AI_SOURCE_TOKENS:
        res.is_ai = res.signature_valid  # only trust AI claim from a valid signature
        res.info = (
            f"C2PA digitalSourceType={token}"
            + ("" if res.signature_valid else " (signature INVALID — not trusted)")
        )
    elif token in _REAL_SOURCE_TOKENS:
        res.info = f"C2PA digitalSourceType={token} (camera/real origin)"
    else:
        res.info = "C2PA manifest present" + (f", digitalSourceType={token}" if token else "")

    return res


def read_c2pa(file_path: str) -> C2paResult:
    """
    Cryptographically verify a file's C2PA manifest. Returns present=False when
    there is no manifest or the native library is unavailable.
    """
    try:
        import json
        from c2pa import Reader
    except Exception:
        return C2paResult(present=False, info="c2pa library unavailable")

    try:
        reader = Reader.from_file(file_path)
    except Exception:
        # No manifest, or unreadable — not an error condition for us.
        return C2paResult(present=False)

    try:
        store = json.loads(reader.json())
    except Exception:
        return C2paResult(present=False)
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    return interpret_manifest_store(store)
