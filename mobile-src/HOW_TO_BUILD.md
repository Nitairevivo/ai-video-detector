# Building the Mobile App

## Setup

```bash
cd mobile
cp ../mobile-src/App.tsx ./App.tsx
cp -r ../mobile-src/components ./components
cp -r ../mobile-src/hooks ./hooks
cp -r ../mobile-src/services ./services

npm install react-native-share-menu
npx expo install expo-clipboard
```

## Update API URL

Edit `services/detector.ts`:
```ts
const API_BASE = "https://YOUR_DEPLOYED_API_URL";
```

## Run on device

```bash
# iOS (requires Mac + Xcode)
npx expo run:ios

# Android
npx expo run:android
```

## Android Overlay Permission

On first launch, the app will ask for "Display over other apps" permission.
This is what enables the floating button.

## iOS Share Extension

In Xcode:
1. File → New → Target → Share Extension
2. Name it "AI Detector Share"
3. The share sheet will show "AI Detector" as an option

## Deploy API to Production

For the mobile app to work anywhere (not just localhost), deploy the Python API:

```bash
# Option 1: Railway (free tier)
railway init && railway up

# Option 2: Render
# Connect GitHub repo → add Python service → set start command:
# uvicorn api.server:app --host 0.0.0.0 --port $PORT
```

Then update `API_BASE` in `services/detector.ts`.
