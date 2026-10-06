#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-.venv-app/bin/python}"
: "${SPARKLE_ROOT:?Set SPARKLE_ROOT to a Sparkle 2.10.0 distribution containing Sparkle.framework and bin/}"
RELEASE_REPOSITORY="${RELEASE_REPOSITORY:-Enishi-Marketing/FilmFilter-main}"
[[ "$RELEASE_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || exit 1
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
VERSION="$(tr -d '[:space:]' < VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
# A distinct Keychain account prevents coupling FilmFilter releases to another app.
PUBLIC_KEY="$("$SPARKLE_ROOT/bin/generate_keys" --account jp.ac.enishi.film-filter -p)"
export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"
"$PYTHON_BIN" -m PyInstaller FilmFilter.spec --clean --noconfirm
APP_PATH="$PWD/dist/Film Filter.app"
SPARKLE_FRAMEWORK="${SPARKLE_FRAMEWORK:-$SPARKLE_ROOT/Sparkle.framework}"
if [ ! -d "$SPARKLE_FRAMEWORK" ]; then
  SPARKLE_FRAMEWORK="$SPARKLE_ROOT/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework"
fi
ditto "$SPARKLE_FRAMEWORK" "$APP_PATH/Contents/Frameworks/Sparkle.framework"
cp assets/Sparkle-LICENSE.txt "$APP_PATH/Contents/Resources/Sparkle-LICENSE.txt"
export APP_PATH PUBLIC_KEY RELEASE_REPOSITORY
"$PYTHON_BIN" - <<'PY'
import os, plistlib, base64
from pathlib import Path
key = os.environ['PUBLIC_KEY'].strip()
assert len(base64.b64decode(key, validate=True)) == 32, 'Invalid Sparkle public key'
p = Path(os.environ['APP_PATH']) / 'Contents/Info.plist'
data = plistlib.loads(p.read_bytes())
data.update(SUFeedURL=f"https://github.com/{os.environ['RELEASE_REPOSITORY']}/releases/latest/download/appcast.xml",
            SUPublicEDKey=key, SUEnableAutomaticChecks=True, SUAutomaticallyUpdate=True,
            SUVerifyUpdateBeforeExtraction=True, SURequireSignedFeed=True)
p.write_bytes(plistlib.dumps(data))
PY
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"
echo "Built $APP_PATH"
