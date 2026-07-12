"""
VerifAI WhatsApp bot — Meta WhatsApp Business Cloud API webhook.

Same strategic advantage as the Telegram bot: when the user sends the video
as a *document*, WhatsApp preserves the original bytes — full metadata and
C2PA signatures included. Sent as a regular video it gets transcoded, and we
say so in the reply.

Setup (Meta developer console → WhatsApp → Configuration):
  1. Webhook URL:      https://<your-api>/whatsapp/webhook
  2. Verify token:     the value of WHATSAPP_VERIFY_TOKEN
  3. Subscribe to the "messages" field.

Env vars:
  WHATSAPP_TOKEN            — permanent system-user access token
  WHATSAPP_PHONE_NUMBER_ID  — the sender phone-number id
  WHATSAPP_VERIFY_TOKEN     — any secret string you choose for the handshake

Stdlib-only (urllib) like the Telegram bot; endpoints are mounted on the main
FastAPI app via `router`.
"""
import json
import os
import re
import tempfile
import traceback
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Request, Response

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()

GRAPH = "https://graph.facebook.com/v20.0"
MAX_MEDIA_BYTES = 60 * 1024 * 1024  # analysis only needs the head of the file anyway

URL_RE = re.compile(r"https?://[^\s]+")

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=3)

# WhatsApp redelivers webhooks until acked and sometimes duplicates them —
# remember recent message ids so a video isn't analyzed (and billed) twice.
_seen_ids: deque = deque(maxlen=500)


def is_configured() -> bool:
    return bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID and VERIFY_TOKEN)


# ─── Graph API helpers ────────────────────────────────────────────────────────

def _graph_get(path: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        f"{GRAPH}/{path}",
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def send_text(to: str, body: str):
    """Send a WhatsApp text message (body uses WhatsApp *bold* markup)."""
    try:
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body[:4000]},
        }).encode()
        req = urllib.request.Request(
            f"{GRAPH}/{PHONE_NUMBER_ID}/messages",
            data=payload,
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        urllib.request.urlopen(req, timeout=20).read()
    except Exception:
        traceback.print_exc()


def download_media(media_id: str, dest: str) -> bool:
    """Resolve a media id to its CDN URL and download the original bytes."""
    try:
        info = _graph_get(media_id)
        url = info.get("url")
        if not url:
            return False
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    # Don't analyze a truncated video — deep layers would run on
                    # a cut file (and possibly lose all frames if moov is last).
                    return False
                f.write(chunk)
        return os.path.getsize(dest) > 1000
    except Exception:
        traceback.print_exc()
        return False


# ─── Result formatting (Hebrew, WhatsApp markup) ──────────────────────────────

def format_result(res: dict, as_document: bool, media: str = "video") -> str:
    noun = "התמונה" if media == "image" else "הסרטון"
    verdict = res.get("verdict", "real")
    pct = round(float(res.get("confidence", 0)) * 100)
    reason = res.get("gemini_reason", "") or (res.get("detection_method", "") or "")[:120]
    tool = res.get("ai_tool_detected") or res.get("edit_tool_detected")

    if verdict == "ai_generated":
        head = "🤖 *נוצר על ידי AI*" + (f" · {tool}" if tool else "")
    elif verdict == "ai_edited":
        head = "✏️ *סרטון אמיתי שנערך עם AI*" + (f" · {tool}" if tool else "")
    else:
        head = "✅ *אותנטי — צילום אמיתי*"

    lines = [head, f"רמת ביטחון: *{pct}%*"]
    if reason:
        lines.append(f"🔍 {reason}")

    signals = res.get("_signals") or {}
    if signals.get("c2pa_is_ai"):
        lines.append("🔏 הקובץ נושא חתימת Content Credentials (C2PA) שמעידה על יצירת AI")
    elif signals.get("has_c2pa"):
        lines.append("🔏 נמצאו Content Credentials (C2PA) בקובץ")
    if signals.get("metadata_is_stripped") or signals.get("platform_reencoded"):
        note = "⚠️ המטא-דאטה המקורי נמחק (פלטפורמה/דחיסה)"
        if not as_document:
            note += f"\n💡 *טיפ:* שלח את {noun} *כמסמך* (📎 ← מסמך/Document) — כך המטא-דאטה המקורי נשמר והבדיקה מדויקת יותר"
        lines.append(note)
    return "\n".join(lines)


WELCOME = (
    "👋 *ברוך הבא ל-VerifAI*\n\n"
    "אני בודק אם *סרטון או תמונה* נוצרו על ידי AI (Sora, Veo, Kling, Midjourney, Firefly, DALL·E…) או אמיתיים.\n\n"
    "*הכי מדויק:* שלח את הסרטון *כמסמך* (📎 ← מסמך/Document) — "
    "כך המטא-דאטה וחתימות ה-C2PA נשמרים.\n"
    "אפשר גם סרטון רגיל או *קישור* (TikTok / YouTube / Instagram…).\n\n"
    "פשוט שלח ותקבל תשובה 👇"
)


# ─── Core processing (runs on the executor) ───────────────────────────────────

def _analyze_media(to: str, media_id: str, filename: str, as_document: bool):
    from api.server import run_fast_analysis, run_full_analysis
    suffix = Path(filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".3gp"):
        suffix = ".mp4"
    tmp = tempfile.mktemp(suffix=suffix)
    try:
        if not download_media(media_id, tmp):
            send_text(to, "❌ לא הצלחתי להוריד את הסרטון. נסה לשלוח שוב.")
            return
        # Original file → intact metadata → fast code-first path is instant and
        # definitive; escalate to full visual analysis only if no code evidence.
        res = run_fast_analysis(tmp)
        if res["verdict"] == "real" and res["confidence"] < 0.5:
            res = run_full_analysis(tmp, deep=True)
        send_text(to, format_result(res, as_document=as_document))
    except Exception as e:
        traceback.print_exc()
        send_text(to, f"❌ שגיאה בניתוח: {str(e)[:120]}")
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


def _analyze_image_media(to: str, media_id: str, filename: str, as_document: bool):
    from api.server import run_image_analysis
    suffix = Path(filename or "image.jpg").suffix.lower() or ".jpg"
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".avif"):
        suffix = ".jpg"
    tmp = tempfile.mktemp(suffix=suffix)
    try:
        if not download_media(media_id, tmp):
            send_text(to, "❌ לא הצלחתי להוריד את התמונה. נסה לשלוח שוב.")
            return
        res = run_image_analysis(tmp)
        send_text(to, format_result(res, as_document=as_document, media="image"))
    except Exception as e:
        traceback.print_exc()
        send_text(to, f"❌ שגיאה בניתוח: {str(e)[:120]}")
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


def _analyze_url(to: str, url: str):
    from api.server import run_full_analysis, download_video_from_url
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        ok, aigc, aigc_info = download_video_from_url(url, tmp)
        if aigc:
            send_text(to, f"🤖 *נוצר על ידי AI*\nרמת ביטחון: *97%*\n🔍 תווית AI של הפלטפורמה: {aigc_info}")
            return
        if not ok:
            send_text(to, "❌ לא הצלחתי להוריד מהקישור. הכי מדויק: שלח לי את קובץ הסרטון עצמו.")
            return
        res = run_full_analysis(tmp, deep=True)
        send_text(to, format_result(res, as_document=True))
    except Exception as e:
        traceback.print_exc()
        send_text(to, f"❌ שגיאה: {str(e)[:120]}")
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


def _handle_message(msg: dict):
    msg_id = msg.get("id")
    if msg_id and msg_id in _seen_ids:
        return
    if msg_id:
        _seen_ids.append(msg_id)

    to = msg.get("from")
    if not to:
        return
    mtype = msg.get("type")

    if mtype == "video":
        _executor.submit(_analyze_media, to, msg["video"]["id"], "video.mp4", False)
    elif mtype == "image":
        _executor.submit(_analyze_image_media, to, msg["image"]["id"], "image.jpg", False)
    elif mtype == "document":
        doc = msg["document"]
        mime = str(doc.get("mime_type", ""))
        if mime.startswith("video/"):
            _executor.submit(_analyze_media, to, doc["id"], doc.get("filename") or "video.mp4", True)
        elif mime.startswith("image/"):
            _executor.submit(_analyze_image_media, to, doc["id"], doc.get("filename") or "image.jpg", True)
        else:
            send_text(to, "המסמך אינו סרטון או תמונה — שלח וידאו (mp4/mov…) או תמונה (jpg/png…) 🎬🖼️")
    elif mtype == "text":
        body = (msg.get("text") or {}).get("body", "")
        urls = URL_RE.findall(body)
        if urls:
            _executor.submit(_analyze_url, to, urls[0])
        else:
            send_text(to, WELCOME)
    # other types (image/audio/sticker…) are ignored silently


# ─── Webhook endpoints ────────────────────────────────────────────────────────

@router.get("/whatsapp/webhook")
async def whatsapp_verify(request: Request):
    """Meta's one-time subscription handshake."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN and VERIFY_TOKEN:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Receives message events. Must ack fast (Meta retries slow webhooks), so
    analysis is dispatched to the executor and the reply is sent when ready.
    """
    if not is_configured():
        return {"status": "not configured"}
    try:
        data = await request.json()
    except Exception:
        return {"status": "ignored"}

    try:
        for entry in data.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                for msg in (change.get("value", {}) or {}).get("messages", []) or []:
                    _handle_message(msg)
    except Exception:
        traceback.print_exc()
    return {"status": "ok"}
