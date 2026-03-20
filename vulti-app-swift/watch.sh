#!/bin/bash
# Watch for source changes and auto-rebuild + relaunch VultiHub
set -e

APP_NAME="VultiHub"
BUILD_DIR=".build/debug"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"

# Check fswatch is installed
if ! command -v fswatch &>/dev/null; then
    echo "Installing fswatch..."
    brew install fswatch
fi

rebuild() {
    echo "$(date +%H:%M:%S) Building..."
    if swift build 2>&1 | tail -3; then
        # Update binary in app bundle
        if [ -d "$APP_BUNDLE" ]; then
            cp "$BUILD_DIR/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
        else
            # First run — use run.sh to create the bundle
            ./run.sh
            return
        fi

        # Relaunch
        pkill -f "$APP_NAME.app/Contents/MacOS/$APP_NAME" 2>/dev/null || true
        sleep 0.3
        open "$APP_BUNDLE"
        echo "$(date +%H:%M:%S) Relaunched"
    else
        echo "$(date +%H:%M:%S) Build failed"
    fi
}

# Initial build + launch
rebuild

# Watch Sources/ for changes, debounce 1s
echo "Watching Sources/ for changes..."
fswatch -o -l 1 Sources/ | while read -r _; do
    rebuild
done
