# VerifAI — Publishing the mobile app to the stores

The app is **store-ready**: `app.json` has the bundle IDs (`com.verifai.app`),
version (1.4.0 / versionCode 14), a 1024×1024 icon, splash, permissions, share
intents and deep links; `eas.json` has a `production` profile that outputs the
exact artifacts the stores want (Android **.aab**, iOS release).

Producing the actual store binary happens on **Expo's build servers (EAS)** and
requires *your* accounts — it can't be done from a sandbox. Here's the whole path.

---

## What you need (one-time)

| For | Account | Cost |
|-----|---------|------|
| Any build | Expo account + access token — https://expo.dev | free |
| Google Play | Google Play Console developer account | $25 once |
| App Store (iOS) | Apple Developer Program | $99 / year |

Get your Expo token: **expo.dev → Settings → Access tokens → Create**.

---

## Option A — one click from GitHub (no local setup)

1. GitHub → **Actions** → **“EAS App Build (store-ready)”** → **Run workflow**.
2. Paste your Expo token, pick `platform: android`, `profile: production`.
3. EAS builds the **.aab** and gives you a download link on expo.dev.

## Option B — from your machine

```bash
cd mobile
npm install
npm install -g eas-cli
eas login                                   # your Expo account
eas build --platform android --profile production   # → .aab
# iOS (needs the Apple account):
eas build --platform ios --profile production        # → .ipa
```

---

## Uploading to the stores

**Google Play:** Play Console → create the app → *Production* → upload the
`.aab`. First release also needs: store listing (name, short/long description,
screenshots), a 512×512 icon, a feature graphic, and the privacy-policy URL —
use the live one: `https://web-zeta-ecru-80.vercel.app/privacy`.

EAS can even upload it for you:
```bash
eas submit --platform android --latest
```

**App Store (iOS):** `eas submit --platform ios --latest`, then finish the
listing in App Store Connect.

---

## Bumping the version for the next release

Edit `mobile/app.json`: raise `expo.version` (e.g. `1.4.1`) and
`expo.android.versionCode` (e.g. `15`) — the stores reject re-uploads of the
same versionCode.
