"""
VerifAI Telegram bot.

The big advantage of Telegram: the user sends us the ACTUAL video file, so we
analyze the complete original bytes — no download, no CDN blocking, no
re-encoding loss. This is the most accurate path in the whole product.

Handles:
  • a video / video-note / video document  → analyze the file directly
  • a text message containing a video URL   → download + analyze (yt-dlp path)
  • /start, /help                            → Hebrew instructions

Runs as a standalone long-polling worker (no webhook, no public URL needed):
    TELEGRAM_BOT_TOKEN=xx: python -m api.telegram_bot
On Railway add a second process:  telegram: python -m api.telegram_bot

Stdlib-only (urllib) so it adds no dependencies and can't crash the API server.
"""
import json
import os
import re
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Point TELEGRAM_API_BASE at a self-hosted Bot API server
# (github.com/tdlib/telegram-bot-api) to lift the 20MB getFile limit to 2GB.
API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
API = f"{API_BASE}/bot{TOKEN}"
FILE_API = f"{API_BASE}/file/bot{TOKEN}"

# The hosted Bot API serves files up to 20 MB; a self-hosted server goes to 2GB.
_SELF_HOSTED = API_BASE != "https://api.telegram.org"
TG_MAX_BYTES = (2000 if _SELF_HOSTED else 20) * 1024 * 1024
TG_MAX_LABEL = "2GB" if _SELF_HOSTED else "20MB"

URL_RE = re.compile(r"https?://[^\s]+")
VIDEO_URL_HINT = re.compile(
    r"(tiktok\.com|instagram\.com|youtube\.com|youtu\.be|facebook\.com|fb\.watch|"
    r"twitter\.com|x\.com|reddit\.com|v\.redd\.it|t\.me|vimeo\.com|snapchat\.com)"
)

_executor = ThreadPoolExecutor(max_workers=3)


# ─── Telegram API helpers (stdlib) ────────────────────────────────────────────

def _get(method: str, params: dict = None, timeout: int = 60):
    url = f"{API}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _post(method: str, data: dict, timeout: int = 30):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{API}/{method}", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def send_message(chat_id, text, reply_to=None):
    try:
        data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": "true"}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        return _post("sendMessage", data)
    except Exception:
        return None


def send_typing(chat_id):
    try:
        _post("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def download_file(file_id: str, dest: str) -> bool:
    """Resolve a Telegram file_id and download it to dest. Returns success."""
    info = _get("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return False
    file_path = info["result"].get("file_path")
    if not file_path:
        return False
    url = f"{FILE_API}/{file_path}"
    req = urllib.request.Request(url, headers={"User-Agent": "VerifAI-Bot"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(dest) > 1000


# ─── Result formatting (Hebrew) ───────────────────────────────────────────────

def format_result(res: dict, as_document: bool = True) -> str:
    verdict = res.get("verdict", "real")
    pct = round(float(res.get("confidence", 0)) * 100)
    method = res.get("detection_method", "")
    reason = res.get("gemini_reason", "")
    tool = res.get("ai_tool_detected") or res.get("edit_tool_detected")

    if verdict == "ai_generated":
        head = "🤖 <b>נוצר על ידי AI</b>"
        if tool:
            head += f" · {tool}"
    elif verdict == "ai_edited":
        head = "✏️ <b>סרטון אמיתי שנערך עם AI</b>"
        if tool:
            head += f" · {tool}"
    else:
        head = "✅ <b>אותנטי — צילום אמיתי</b>"

    lines = [head, f"רמת ביטחון: <b>{pct}%</b>"]
    if reason:
        lines.append(f"👁️ {reason}")
    elif method:
        lines.append(f"🔍 {method[:120]}")
    layers = res.get("ensemble_layers") or {}
    if layers:
        pretty = ", ".join(f"{k}={round(float(v)*100)}%" for k, v in layers.items())
        lines.append(f"<i>שכבות: {pretty}</i>")

    # Provenance notes — what the file's own "code" (metadata) tells us
    signals = res.get("_signals") or {}
    if signals.get("c2pa_is_ai"):
        lines.append("🔏 הקובץ נושא חתימת Content Credentials (C2PA) שמעידה על יצירת AI — הוכחה קריפטוגרפית")
    elif signals.get("has_c2pa"):
        lines.append("🔏 נמצאו Content Credentials (C2PA) בקובץ")
    if signals.get("metadata_is_stripped") or signals.get("platform_reencoded"):
        note = "⚠️ המטא-דאטה המקורי של הקובץ נמחק (כנראה עבר דרך פלטפורמה/דחיסה)"
        if not as_document:
            note += "\n💡 <b>טיפ:</b> שלח את הסרטון <b>כקובץ</b> (📎 ← קובץ/File, בלי דחיסה) — כך כל המטא-דאטה המקורי נשמר והבדיקה מדויקת יותר"
        lines.append(note)
    return "\n".join(lines)


# ─── Core processing ──────────────────────────────────────────────────────────

def _analyze_file(chat_id, msg_id, file_id, filename, as_document=False):
    from api.server import run_full_analysis
    suffix = Path(filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"):
        suffix = ".mp4"
    tmp = tempfile.mktemp(suffix=suffix)
    try:
        if not download_file(file_id, tmp):
            send_message(chat_id, "❌ לא הצלחתי להוריד את הסרטון. נסה לשלוח שוב.", msg_id)
            return
        res = run_full_analysis(tmp, deep=True)
        send_message(chat_id, format_result(res, as_document=as_document), msg_id)
    except Exception as e:
        traceback.print_exc()
        send_message(chat_id, f"❌ שגיאה בניתוח: {str(e)[:120]}", msg_id)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


def _analyze_url(chat_id, msg_id, url):
    from api.server import run_full_analysis, download_video_from_url
    tmp = tempfile.mktemp(suffix=".mp4")
    try:
        ok, aigc, aigc_info = download_video_from_url(url, tmp)
        if aigc:
            send_message(chat_id,
                         f"🤖 <b>נוצר על ידי AI</b>\nרמת ביטחון: <b>97%</b>\n🔍 תווית AIGC של הפלטפורמה: {aigc_info}",
                         msg_id)
            return
        if not ok:
            send_message(chat_id,
                         "❌ לא הצלחתי להוריד מהקישור. הכי מדויק: שלח לי את קובץ הסרטון עצמו כאן בטלגרם.",
                         msg_id)
            return
        res = run_full_analysis(tmp, deep=True)
        send_message(chat_id, format_result(res), msg_id)
    except Exception as e:
        traceback.print_exc()
        send_message(chat_id, f"❌ שגיאה: {str(e)[:120]}", msg_id)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


WELCOME = (
    "👋 <b>ברוך הבא ל-VerifAI</b>\n\n"
    "אני בודק אם סרטון נוצר על ידי AI (Sora, Veo, Kling, Runway…) או אמיתי.\n\n"
    "<b>הכי מדויק:</b> שלח לי את הסרטון <b>כקובץ</b> (📎 ← קובץ/File, בלי דחיסה) — "
    "כך אני מקבל את הבייטים המקוריים עם כל המטא-דאטה וחתימות ה-C2PA, "
    "והבדיקה הכי מדויקת שיש.\n"
    "שליחה כסרטון רגיל עובדת גם, אבל טלגרם דוחס ומוחק חלק מהמידע.\n"
    "אפשר גם לשלוח <b>קישור</b> (TikTok / YouTube / Instagram…), ואני אוריד ואנתח.\n\n"
    "פשוט שלח סרטון או קישור ותקבל תשובה 👇"
)


def handle_update(update: dict):
    try:
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        msg_id = msg.get("message_id")
        text = msg.get("text", "") or msg.get("caption", "") or ""

        if text.strip() in ("/start", "/help"):
            send_message(chat_id, WELCOME, msg_id)
            return

        # 1) Actual video file (best path)
        # A video sent as a DOCUMENT (📎 → File) keeps the original bytes and
        # metadata intact; sent as a regular "video" Telegram's client
        # compresses/re-encodes it and the original metadata is lost.
        video = msg.get("video") or msg.get("video_note")
        doc = msg.get("document")
        as_document = False
        if not video and doc and str(doc.get("mime_type", "")).startswith("video/"):
            video = doc
            as_document = True

        if video:
            size = int(video.get("file_size", 0) or 0)
            if size and size > TG_MAX_BYTES:
                send_message(chat_id,
                             f"⚠️ הסרטון גדול מ-{TG_MAX_LABEL} — טלגרם לא נותן לבוט להוריד קבצים כאלה.\n"
                             "שלח קליפ קצר יותר, או שלח לי קישור לסרטון.", msg_id)
                return
            send_typing(chat_id)
            fname = video.get("file_name") or "video.mp4"
            _executor.submit(_analyze_file, chat_id, msg_id, video["file_id"], fname, as_document)
            return

        # 2) URL in the text
        urls = URL_RE.findall(text)
        vid_url = next((u for u in urls if VIDEO_URL_HINT.search(u)), urls[0] if urls else None)
        if vid_url:
            send_typing(chat_id)
            _executor.submit(_analyze_url, chat_id, msg_id, vid_url)
            return

        # 3) Anything else
        if text:
            send_message(chat_id,
                         "שלח לי <b>סרטון</b> (קובץ) או <b>קישור</b> לסרטון ואבדוק אם הוא AI 🤖",
                         msg_id)
    except Exception:
        traceback.print_exc()


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    me = _get("getMe")
    if not me.get("ok"):
        print(f"ERROR: bad token / getMe failed: {me}", file=sys.stderr)
        sys.exit(1)
    print(f"VerifAI Telegram bot online as @{me['result'].get('username')}")

    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            resp = _get("getUpdates", params, timeout=60)
            if not resp.get("ok"):
                time.sleep(2)
                continue
            for update in resp["result"]:
                offset = update["update_id"] + 1
                handle_update(update)
        except Exception:
            traceback.print_exc()
            time.sleep(3)


if __name__ == "__main__":
    main()
