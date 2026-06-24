#!/bin/bash
# Builds chrome-extension.zip for Chrome Web Store upload
# Run: bash chrome-extension/build.sh

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/../chrome-extension.zip"

echo "Building Chrome extension..."
cd "$DIR"

# Remove old build
rm -f "$OUT"

# Create zip (exclude source control and build artifacts)
zip -r "$OUT" . \
  --exclude "*.DS_Store" \
  --exclude ".git*" \
  --exclude "build.sh" \
  --exclude "*.map" \
  --exclude "node_modules/*"

SIZE=$(du -sh "$OUT" | cut -f1)
echo "✓ Built: chrome-extension.zip ($SIZE)"
echo ""
echo "Upload to: https://chrome.google.com/webstore/devconsole"
echo "  1. New item → Upload → select chrome-extension.zip"
echo "  2. Store listing → fill description below"
echo ""
echo "=== STORE LISTING ==="
cat "$DIR/store-listing.md"
