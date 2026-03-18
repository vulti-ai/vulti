#!/usr/bin/env bash
# Build or download the Continuwuity binary for the current platform.
# Places the binary at src-tauri/binaries/continuwuity-{target-triple}
#
# Usage:
#   ./scripts/build-continuwuity.sh              # auto-detect target
#   ./scripts/build-continuwuity.sh aarch64-apple-darwin  # explicit target

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BINARIES_DIR="$REPO_DIR/src-tauri/binaries"
CONTINUWUITY_REPO="continuwuity/continuwuity"

# Determine target triple
if [ -n "${1:-}" ]; then
    TARGET="$1"
else
    TARGET="$(rustc -vV | grep host | cut -d' ' -f2)"
fi

OUTPUT="$BINARIES_DIR/continuwuity-$TARGET"
echo "Building continuwuity for $TARGET → $OUTPUT"

mkdir -p "$BINARIES_DIR"

# --- Try downloading a prebuilt binary ---
download_binary() {
    echo "Checking for prebuilt binary..."

    case "$TARGET" in
        *linux*aarch64* | *linux*arm64*)  PATTERN="linux-arm64" ;;
        *linux*x86_64* | *linux*amd64*)   PATTERN="linux-amd64" ;;
        *darwin* | *apple*)               PATTERN="" ;;  # No macOS prebuilts
        *)                                PATTERN="" ;;
    esac

    [ -z "$PATTERN" ] && return 1

    # Search recent releases for a matching asset
    RELEASES=$(curl -sf "https://api.github.com/repos/$CONTINUWUITY_REPO/releases?per_page=5" || echo "[]")

    URL=$(echo "$RELEASES" | python3 -c "
import sys, json
releases = json.load(sys.stdin)
for r in releases:
    for a in r.get('assets', []):
        name = a['name'].lower()
        if '$PATTERN' in name and 'maxperf' not in name and not name.endswith(('.sha256', '.sig')):
            print(a['browser_download_url'])
            sys.exit(0)
sys.exit(1)
" 2>/dev/null) || return 1

    echo "Downloading $URL"
    curl -fSL "$URL" -o "$OUTPUT"
    chmod +x "$OUTPUT"
    echo "Downloaded prebuilt binary"
    return 0
}

# --- Build from source ---
build_from_source() {
    echo "Building from source (this may take several minutes)..."

    BUILD_DIR="/tmp/continuwuity-build"

    if [ -d "$BUILD_DIR/.git" ]; then
        echo "Updating source..."
        cd "$BUILD_DIR" && git pull --ff-only
    else
        echo "Cloning source..."
        rm -rf "$BUILD_DIR"
        git clone --depth 1 "https://github.com/$CONTINUWUITY_REPO.git" "$BUILD_DIR"
    fi

    cd "$BUILD_DIR"

    if [ "$TARGET" = "$(rustc -vV | grep host | cut -d' ' -f2)" ]; then
        cargo build --release
    else
        cargo build --release --target "$TARGET"
    fi

    # Find the built binary
    for name in continuwuity conduwuit conduit; do
        BUILT="$BUILD_DIR/target/release/$name"
        [ -f "$BUILT" ] || BUILT="$BUILD_DIR/target/$TARGET/release/$name"
        if [ -f "$BUILT" ]; then
            cp "$BUILT" "$OUTPUT"
            chmod +x "$OUTPUT"
            echo "Built from source"
            return 0
        fi
    done

    echo "ERROR: Build succeeded but binary not found"
    return 1
}

# --- Main ---
if [ -f "$OUTPUT" ] && [ -x "$OUTPUT" ]; then
    echo "Binary already exists at $OUTPUT"
    exit 0
fi

download_binary || build_from_source || {
    echo "ERROR: Could not obtain continuwuity binary for $TARGET"
    echo "Install Rust (https://rustup.rs) and try again, or download manually."
    exit 1
}

echo "Done: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
