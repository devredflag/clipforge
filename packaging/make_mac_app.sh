#!/bin/bash
# Empacota dist/ClipForge em um ClipForge.app arrastável para a pasta Aplicativos.
set -e
cd "$(dirname "$0")/.."
SRC="dist/ClipForge"
APP="dist/ClipForge.app"
[ -d "$SRC" ] || { echo "Rode build_mac.command primeiro."; exit 1; }
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R "$SRC/." "$APP/Contents/MacOS/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ClipForge</string>
  <key>CFBundleDisplayName</key><string>ClipForge</string>
  <key>CFBundleIdentifier</key><string>com.clipforge.app</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>ClipForge</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
echo "Criado: $APP  (arraste para a pasta Aplicativos)"
