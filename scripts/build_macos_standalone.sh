#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

APP_NAME="BaVa Downloader"
export PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/tmp/pyinstaller"
mkdir -p "$PYINSTALLER_CONFIG_DIR"

rm -rf build "$APP_NAME.spec" dist/"$APP_NAME" dist/"$APP_NAME.app" dist/"$APP_NAME-macos.zip"

./myenv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "static/icons/app.icns" \
  --add-data "templates:templates" \
  --add-data "static:static" \
  app_launcher.py

cd dist
zip -qr "$APP_NAME-macos.zip" "$APP_NAME.app"

echo "Built: $PROJECT_ROOT/dist/$APP_NAME.app"
echo "Zip:   $PROJECT_ROOT/dist/$APP_NAME-macos.zip"
