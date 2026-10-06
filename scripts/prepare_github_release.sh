#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SPARKLE_ROOT:?Set SPARKLE_ROOT to the Sparkle distribution}"
RELEASE_REPOSITORY="${RELEASE_REPOSITORY:-Enishi-Marketing/FilmFilter-main}"
VERSION="$(tr -d '[:space:]' < VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
[[ "$RELEASE_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || exit 1
FEED="$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' 'dist/Film Filter.app/Contents/Info.plist')"
[[ "$FEED" == "https://github.com/$RELEASE_REPOSITORY/releases/latest/download/appcast.xml" ]] || { echo 'Rebuild with the matching RELEASE_REPOSITORY'; exit 1; }
APP_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' 'dist/Film Filter.app/Contents/Info.plist')"
[[ "$APP_VERSION" == "$VERSION" ]] || { echo 'Rebuild after changing VERSION'; exit 1; }
STAGE="$PWD/build/github-release"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp "dist/Film.Filter.v$VERSION.dmg" "$STAGE/"
(cd "$STAGE" && shasum -a 256 "Film.Filter.v$VERSION.dmg" > "Film.Filter.v$VERSION.dmg.sha256")
"$SPARKLE_ROOT/bin/generate_appcast" --account jp.ac.enishi.film-filter \
  --download-url-prefix "https://github.com/$RELEASE_REPOSITORY/releases/download/v$VERSION/" \
  --maximum-deltas 0 -o "$STAGE/appcast.xml" "$STAGE"
echo "Upload all files in $STAGE to GitHub Release v$VERSION."
