#!/bin/bash
# Downloads AI-generated and real videos for training
# Usage: bash download_training_data.sh

AI_DIR="/Users/nitai/Desktop/dataset/AI_Videos"
REAL_DIR="/Users/nitai/Desktop/dataset/Real_Videos"
mkdir -p "$AI_DIR" "$REAL_DIR"

OPTS="--no-playlist -f mp4 --max-filesize 50m -o '%(title)s [%(id)s].%(ext)s' --quiet --progress"

echo "=== Downloading AI-generated videos ==="

AI_URLS=(
  # Sora demos
  "https://www.youtube.com/watch?v=HK6y8DAPN_0"
  "https://www.youtube.com/watch?v=iQDHENxNbgY"
  "https://www.youtube.com/watch?v=ByFbAEjyThM"
  # Runway Gen-3
  "https://www.youtube.com/watch?v=UtEBme2FIOQ"
  "https://www.youtube.com/watch?v=3TBvp_zp_sU"
  # Kling AI
  "https://www.youtube.com/watch?v=WVrpUKNaRsc"
  "https://www.youtube.com/watch?v=7lEKDUaXqRY"
  # Pika Labs
  "https://www.youtube.com/watch?v=DJ7N0OAqQiM"
  "https://www.youtube.com/watch?v=CxGQkFT3vBM"
  # Luma Dream Machine
  "https://www.youtube.com/watch?v=LlqzFHuDhxo"
  "https://www.youtube.com/watch?v=kSZzp_nImJA"
  # Hailuo / MiniMax
  "https://www.youtube.com/watch?v=J6KDBFHmQXA"
  # Deepfakes
  "https://www.youtube.com/watch?v=mSaIrz8lM1U"
  # AI shorts compilations
  "https://www.youtube.com/watch?v=FvMVob8sAOQ"
  "https://www.youtube.com/watch?v=8HYR6ce4jxM"
  "https://www.youtube.com/watch?v=7JuHJbVVgH4"
  "https://www.youtube.com/watch?v=Q0ppOmJqRno"
  "https://www.youtube.com/watch?v=mSaIrz8lM1U"
  "https://www.youtube.com/watch?v=r1GSkSRM3Cs"
  "https://www.youtube.com/watch?v=WbAVAVTosEk"
)

for url in "${AI_URLS[@]}"; do
  echo "→ AI: $url"
  yt-dlp $OPTS -o "$AI_DIR/%(title)s [%(id)s].%(ext)s" "$url" 2>/dev/null || echo "  ✗ skipped"
done

echo ""
echo "=== Downloading real/camera videos ==="

REAL_URLS=(
  # Real travel/nature
  "https://www.youtube.com/watch?v=LXb3EKWsInQ"
  "https://www.youtube.com/watch?v=iRkgSFRcJsI"
  "https://www.youtube.com/watch?v=6d8F4FKf_R4"
  "https://www.youtube.com/watch?v=0OhHb49YnqM"
  "https://www.youtube.com/watch?v=v1NHlTlmRxo"
  # Real cinema/film
  "https://www.youtube.com/watch?v=VYOjWnS4cMY"
  "https://www.youtube.com/watch?v=s_3idASHb-0"
  "https://www.youtube.com/watch?v=2vj37yeQQHg"
  "https://www.youtube.com/watch?v=Wt5rMQeRQ_8"
  "https://www.youtube.com/watch?v=O-MU02iKxhQ"
  # Real sports/action
  "https://www.youtube.com/watch?v=9bZkp7q19f0"
  "https://www.youtube.com/watch?v=RgKAFK5djSk"
  "https://www.youtube.com/watch?v=JGwWNGJdvx8"
  # Real vlogs
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  "https://www.youtube.com/watch?v=gG_dA32oH44"
  "https://www.youtube.com/watch?v=pSCJvJ0HE98"
  "https://www.youtube.com/watch?v=hFZFjoX2cGg"
  "https://www.youtube.com/watch?v=TJAqeJewYNo"
  "https://www.youtube.com/watch?v=Vhh_GeBPOhs"
  "https://www.youtube.com/watch?v=6_b7RDuLwcI"
)

for url in "${REAL_URLS[@]}"; do
  echo "→ Real: $url"
  yt-dlp $OPTS -o "$REAL_DIR/%(title)s [%(id)s].%(ext)s" "$url" 2>/dev/null || echo "  ✗ skipped"
done

echo ""
echo "=== Done ==="
echo "AI videos:   $(ls "$AI_DIR"/*.mp4 2>/dev/null | wc -l)"
echo "Real videos: $(ls "$REAL_DIR"/*.mp4 2>/dev/null | wc -l)"
