#!/bin/bash
# Build and run VultiHub as a proper macOS .app bundle
# This ensures the app gets its own window focus and keyboard input
set -e

APP_NAME="VultiHub"
BUILD_DIR=".build/debug"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

# Build
swift build

# Create .app bundle structure
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS" "$RESOURCES"

# Copy binary
cp "$BUILD_DIR/$APP_NAME" "$MACOS/$APP_NAME"

# Copy any resources from the build
if [ -d "$BUILD_DIR/VultiHub_VultiHub.bundle" ]; then
    cp -R "$BUILD_DIR/VultiHub_VultiHub.bundle" "$RESOURCES/"
fi

# Write Info.plist
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>VultiHub</string>
    <key>CFBundleIdentifier</key>
    <string>com.vulti.hub</string>
    <key>CFBundleName</key>
    <string>VultiHub</string>
    <key>CFBundleDisplayName</key>
    <string>VultiHub</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
    </dict>
    <key>NSLocalNetworkUsageDescription</key>
    <string>VultiHub connects to the local gateway service.</string>
    <key>NSDocumentsFolderUsageDescription</key>
    <string>VultiHub agents need access to your Documents folder to read and manage files on your behalf.</string>
    <key>NSDownloadsFolderUsageDescription</key>
    <string>VultiHub agents need access to your Downloads folder to read and manage files on your behalf.</string>
    <key>NSDesktopFolderUsageDescription</key>
    <string>VultiHub agents need access to your Desktop to read and manage files on your behalf.</string>
</dict>
</plist>
PLIST

echo "Built $APP_BUNDLE"

# Re-sign so macOS renders at Retina resolution on Apple Silicon
codesign --force --sign - --deep "$APP_BUNDLE" 2>/dev/null || true

# Kill any existing instance
pkill -f "$APP_NAME.app/Contents/MacOS/$APP_NAME" 2>/dev/null || true
sleep 0.3

# Launch as a proper app (gets its own dock icon, window focus, keyboard input)
open "$APP_BUNDLE"
