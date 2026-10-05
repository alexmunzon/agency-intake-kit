#!/usr/bin/env bash
# Makes docs/screenshots/demo.gif from the committed demo run.
# Needs ffmpeg (https://ffmpeg.org). Run from the repo root: npm run demo-gif
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO_DIR="$ROOT/docs/screenshots/.demo-video"
GIF="$ROOT/docs/screenshots/demo.gif"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is not installed, so the GIF cannot be made. Install it, then rerun npm run demo-gif." >&2
  exit 1
fi
rm -rf "$VIDEO_DIR"
(cd "$ROOT/dashboard" && npx playwright test e2e/demo-gif.spec.ts)
ffmpeg -y -loglevel error -i "$VIDEO_DIR/demo.webm" \
  -vf "fps=6,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none" \
  -loop 0 "$GIF"
rm -rf "$VIDEO_DIR"
BYTES=$(wc -c < "$GIF" | tr -d ' ')
echo "Wrote docs/screenshots/demo.gif ($BYTES bytes)"
if [ "$BYTES" -gt 3000000 ]; then
  echo "demo.gif is over 3 MB. Lower fps or scale in scripts/demo-gif.sh." >&2
  exit 1
fi
