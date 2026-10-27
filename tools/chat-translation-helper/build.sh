#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
APP="dist/Minecraft Bilingual Helper.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" work/module-cache
ARCH="$(uname -m)"
swiftc -O -swift-version 5 -target "$ARCH-apple-macos15.0" \
  -module-cache-path work/module-cache -parse-as-library \
  Sources/HTTPProtocol.swift Sources/LanguageIdentity.swift Sources/ServiceDiagnostics.swift Sources/TranslationQueue.swift Sources/LocalServer.swift Sources/App.swift \
  -o "$APP/Contents/MacOS/MinecraftBilingualHelper" \
  -framework SwiftUI -framework Translation -framework NaturalLanguage -framework Network -framework AppKit
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>MinecraftBilingualHelper</string>
  <key>CFBundleIdentifier</key><string>dev.minecraft.bilingual.helper</string>
  <key>CFBundleName</key><string>Minecraft Bilingual Helper</string>
  <key>CFBundleDisplayName</key><string>Minecraft 双语翻译助手</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.4</string>
  <key>CFBundleVersion</key><string>5</string>
  <key>LSMinimumSystemVersion</key><string>15.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
echo "Built: $PWD/$APP"
