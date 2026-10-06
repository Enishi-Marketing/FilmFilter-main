#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
scripts/build_macos_app.sh
VERSION="$(tr -d '[:space:]' < VERSION)"
STAGE="$PWD/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto 'dist/Film Filter.app' "$STAGE/Film Filter.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname 'Film Filter' -srcfolder "$STAGE" -ov -format UDZO "dist/Film.Filter.v$VERSION.dmg"
