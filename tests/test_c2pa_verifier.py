"""
Tests for analyzer/c2pa_verifier.py — manifest interpretation only.

These exercise the pure logic (interpret_manifest_store) against realistic
C2PA manifest-store JSON, so they run on any Python version without the native
c2pa library.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer.c2pa_verifier import interpret_manifest_store, _source_token


IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def _store(source_type, validation=None, action="c2pa.created", generator="Firefly"):
    manifest = {
        "claim_generator_info": [{"name": generator}],
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {"actions": [{"action": action, "digitalSourceType": IPTC + source_type}]},
            }
        ],
    }
    store = {"active_manifest": "urn:m1", "manifests": {"urn:m1": manifest}}
    if validation is not None:
        store["validation_status"] = [{"code": c} for c in validation]
    return store


def test_valid_ai_manifest_flags_ai():
    r = interpret_manifest_store(_store("trainedAlgorithmicMedia"))
    assert r.present and r.signature_valid and r.is_ai
    assert r.digital_source_type.endswith("trainedAlgorithmicMedia")
    assert r.claim_generator == "Firefly"


def test_composite_ai_flags_ai():
    r = interpret_manifest_store(_store("compositeWithTrainedAlgorithmicMedia"))
    assert r.is_ai


def test_camera_capture_is_not_ai():
    r = interpret_manifest_store(_store("digitalCapture"))
    assert r.present and r.signature_valid and not r.is_ai
    assert "camera/real origin" in r.info


def test_ai_type_but_invalid_signature_is_not_trusted():
    # AI digitalSourceType but the signature failed to validate → do NOT flag AI
    r = interpret_manifest_store(
        _store("trainedAlgorithmicMedia", validation=["signingCredential.untrusted"])
    )
    assert r.present and not r.signature_valid and not r.is_ai
    assert "not trusted" in r.info.lower()


def test_mismatch_code_invalidates_signature():
    r = interpret_manifest_store(
        _store("trainedAlgorithmicMedia", validation=["claimSignature.mismatch"])
    )
    assert not r.signature_valid and not r.is_ai


def test_success_only_codes_keep_signature_valid():
    r = interpret_manifest_store(
        _store("trainedAlgorithmicMedia",
               validation=["claimSignature.validated", "signingCredential.trusted"])
    )
    assert r.signature_valid and r.is_ai


def test_empty_store_not_present():
    r = interpret_manifest_store({"active_manifest": None, "manifests": {}})
    assert not r.present


def test_manifest_without_active_pointer_still_read():
    store = _store("trainedAlgorithmicMedia")
    store.pop("active_manifest")
    r = interpret_manifest_store(store)
    assert r.present and r.is_ai


def test_source_token_extraction():
    assert _source_token(IPTC + "trainedAlgorithmicMedia") == "trainedalgorithmicmedia"
    assert _source_token("") == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok - {fn.__name__}")
    print(f"{len(fns)} tests passed")
