# Private cobalt for VerifAI — make link detection read the real code

VerifAI's detection is built on the **code behind the video** — C2PA
credentials, platform AIGC labels, container/metadata fingerprints. Reading
those needs the **original file**. When a user uploads or shares a file we have
it. When they paste a **link**, someone has to fetch the original — and
YouTube/TikTok block our server's datacenter IP.

A private **cobalt** instance solves this: it fetches the original upstream and
tunnels the bytes back to VerifAI, which then reads the real code. This is the
"option 3" path — fully in your control, no per-request cost.

## What works after this

| Platform | Link works? |
|----------|-------------|
| TikTok, Instagram, X/Twitter, Reddit, Facebook, Vimeo… | ✅ out of the box |
| YouTube | ✅ **after adding cookies** (step 4) — Google blocks datacenter IPs harder |

## Deploy (≈10 minutes)

1. **Get a host with Docker.** Cheapest reliable options: a $4–6/mo VPS
   (Hetzner, DigitalOcean), Fly.io, or Railway. A residential/home box is even
   better for YouTube.

2. **Generate an API key** (keep it secret):
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(24))"
   ```
   Put it in `keys.json` next to the compose file:
   ```json
   { "<PASTE_KEY_HERE>": { "name": "verifai", "limit": 1000 } }
   ```

3. **Start it:**
   ```bash
   COBALT_PUBLIC_URL="https://cobalt.yourdomain.com" docker compose up -d
   ```
   (or expose port 9000 behind any HTTPS reverse proxy / the host's TLS)

4. **YouTube only — add cookies** so Google lets the instance in:
   - Install a "Get cookies.txt" browser extension, open youtube.com logged in,
     export, and convert to cobalt's JSON format (see cobalt docs
     `docs/run-an-instance.md` → cookies). Save as `cookies.json` here.
   - Without this, YouTube links may still fail; everything else works.

5. **Point VerifAI at it** — set these env vars on the main app (Railway →
   VerifAI service → Variables), no redeploy of code needed:
   ```
   COBALT_INSTANCES = cobalt.yourdomain.com
   COBALT_API_KEY   = <the key from step 2>
   ```
   VerifAI already calls cobalt first for platform links (see
   `_download_via_cobalt` in `api/server.py`).

## Verify it works

Trigger the repo's **"Verify link→video download"** GitHub Action with any
YouTube/TikTok URL — with `COBALT_INSTANCES`/`COBALT_API_KEY` set it will report
`[cobalt] SUCCESS` and `FULL CHAIN: ok=True`.

## The even-simpler alternative

If you'd rather not run a service: set **`YTDLP_PROXY`** on the VerifAI app to a
residential proxy (a few $/mo). yt-dlp then routes through a residential IP and
downloads directly — no cobalt needed. Both levers are already wired.
