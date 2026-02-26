#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
APP_NAME="BaVa Downloader"
APP_EXECUTABLE="BaVaDownloader"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
APP_RES_DIR="$RESOURCES_DIR/app"
RUNTIME_DIR="$RESOURCES_DIR/runtime"

rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR" "$APP_RES_DIR" "$RUNTIME_DIR"

# Copy application source
cp "$PROJECT_ROOT/main.py" "$APP_RES_DIR/main.py"
cp -R "$PROJECT_ROOT/templates" "$APP_RES_DIR/templates"
cp -R "$PROJECT_ROOT/static" "$APP_RES_DIR/static"
cp "$PROJECT_ROOT/requirements.txt" "$APP_RES_DIR/requirements.txt"
cp "$PROJECT_ROOT/static/icons/app.icns" "$RESOURCES_DIR/app.icns"

# Bundle current virtual environment for offline execution
cp -R "$PROJECT_ROOT/myenv" "$RUNTIME_DIR/myenv"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>BaVaDownloader</string>
  <key>CFBundleIdentifier</key>
  <string>com.bava.downloader.app</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleIconFile</key>
  <string>app.icns</string>
  <key>CFBundleName</key>
  <string>BaVa Downloader</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/$APP_EXECUTABLE" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$APP_ROOT/Resources/runtime/myenv/bin/python"
APP_DIR="$APP_ROOT/Resources/app"
LOG_DIR="$HOME/Library/Logs/BaVaDownloader"
LOG_FILE="$LOG_DIR/app.log"

mkdir -p "$LOG_DIR"
export FLASK_HOST="127.0.0.1"
export FLASK_PORT="5252"
export FLASK_DEBUG="false"

cd "$APP_DIR"

# Open browser after server starts
(
  for _ in {1..60}; do
    if nc -z 127.0.0.1 5252 >/dev/null 2>&1; then
      open "http://127.0.0.1:5252/" >/dev/null 2>&1 || true
      exit 0
    fi
    sleep 0.25
  done
) &

exec "$PYTHON_BIN" "$APP_DIR/main.py" >>"$LOG_FILE" 2>&1
LAUNCHER

chmod +x "$MACOS_DIR/$APP_EXECUTABLE"

# Optional zip artifact for sharing
cd "$DIST_DIR"
rm -f "$APP_NAME-macos.zip"
zip -qr "$APP_NAME-macos.zip" "$APP_NAME.app"

echo "Built: $APP_BUNDLE"
echo "Zip:   $DIST_DIR/$APP_NAME-macos.zip"
