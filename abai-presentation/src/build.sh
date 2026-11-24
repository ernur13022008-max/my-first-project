#!/usr/bin/env bash
# Rebuild both presentation files from src/deck.html.
# Needs: python3 with Pillow, python-pptx, lxml; Node.js with Playwright (Chromium).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 src/build_show.py build                                  # -> Abai_Qunanbaiuly_show.html
node src/export_layers.js Abai_Qunanbaiuly_show.html build/layers # -> slide layers rendered at 2x
python3 src/build_pptx.py build/layers Abai_Qunanbaiuly.pptx      # -> PowerPoint with transitions and animations
