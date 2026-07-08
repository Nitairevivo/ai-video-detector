"""Unit tests for the WhatsApp webhook — handshake, routing, dedupe, formatting."""
import os
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify"
os.environ["WHATSAPP_TOKEN"] = "test-token"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "12345"

import api.whatsapp_bot as wb
importlib.reload(wb)

from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(wb.router)
client = TestClient(app)


def test_handshake_accepts_correct_token():
    r = client.get("/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "test-verify", "hub.challenge": "42",
    })
    assert r.status_code == 200
    assert r.text == "42"


def test_handshake_rejects_wrong_token():
    r = client.get("/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42",
    })
    assert r.status_code == 403


def test_webhook_acks_empty_payload():
    r = client.post("/whatsapp/webhook", json={"entry": []})
    assert r.status_code == 200


def test_message_dedupe(monkeypatch):
    calls = []
    monkeypatch.setattr(wb._executor, "submit", lambda fn, *a: calls.append(a))
    msg = {"id": "wamid.dup", "from": "972500000000", "type": "video",
           "video": {"id": "media1"}}
    wb._handle_message(msg)
    wb._handle_message(msg)  # duplicate delivery
    assert len(calls) == 1


def test_video_routes_as_compressed_document_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(wb._executor, "submit", lambda fn, *a: calls.append(a))
    wb._handle_message({"id": "wamid.v1", "from": "972", "type": "video",
                        "video": {"id": "m1"}})
    wb._handle_message({"id": "wamid.d1", "from": "972", "type": "document",
                        "document": {"id": "m2", "mime_type": "video/mp4", "filename": "a.mp4"}})
    assert calls[0][3] is False   # regular video → transcoded
    assert calls[1][3] is True    # document → original bytes


def test_url_message_routes_to_url_analyzer(monkeypatch):
    calls = []
    monkeypatch.setattr(wb._executor, "submit", lambda fn, *a: calls.append((fn, a)))
    wb._handle_message({"id": "wamid.u1", "from": "972", "type": "text",
                        "text": {"body": "check https://www.tiktok.com/@x/video/1"}})
    fn, args = calls[0]
    assert fn is wb._analyze_url
    assert "tiktok.com" in args[1]


def test_format_result_document_hides_tip():
    res = {"verdict": "real", "confidence": 0.1,
           "_signals": {"metadata_is_stripped": 1}}
    as_doc = wb.format_result(res, as_document=True)
    as_video = wb.format_result(res, as_document=False)
    assert "טיפ" not in as_doc
    assert "טיפ" in as_video
