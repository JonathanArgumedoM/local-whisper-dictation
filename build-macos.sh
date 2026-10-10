#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
rm -rf build dist
python -m PyInstaller packaging/local-whisper-dictation-macos.spec --clean --noconfirm
cp config.json dist/TravelDeskWhisper.app/Contents/Resources/config.json
cp README.md dist/TravelDeskWhisper.app/Contents/Resources/README.md
echo "Build listo en dist/TravelDeskWhisper.app"