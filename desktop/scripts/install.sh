#!/usr/bin/env bash
# Installer for Ressy Desktop on Linux and macOS (Python 3.10+).
set -euo pipefail

OS="$(uname -s)"
INSTALL_DIR="${RESSY_HOME:-$HOME/.local/share/ressy}"
BIN_DIR="$HOME/.local/bin"

echo "=== Ressy installer ($OS) ==="

PYTHON_BIN=""
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v "$cand")"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Error: Python 3.10+ is required. Install Python first and re-run this script."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REQ_FILE="$REPO_ROOT/desktop/requirements.txt"

if [ ! -f "$REQ_FILE" ]; then
  echo "Error: cannot find $REQ_FILE"
  exit 1
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
if [ "$REPO_ROOT" != "$INSTALL_DIR/src" ]; then
  rm -rf "$INSTALL_DIR/src"
  mkdir -p "$INSTALL_DIR/src"
  cp -R "$REPO_ROOT/desktop" "$INSTALL_DIR/src/desktop"
  [ -d "$REPO_ROOT/server" ] && cp -R "$REPO_ROOT/server" "$INSTALL_DIR/src/server" || true
  [ -f "$REPO_ROOT/LICENSE" ] && cp "$REPO_ROOT/LICENSE" "$INSTALL_DIR/src/LICENSE" || true
fi

if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
  brew list portaudio >/dev/null 2>&1 || brew install portaudio || true
fi

"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/src/desktop/requirements.txt"

cat > "$BIN_DIR/ressy" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$INSTALL_DIR/src/desktop\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$INSTALL_DIR/venv/bin/python" -m ressy "\$@"
EOF
chmod +x "$BIN_DIR/ressy"

if [ "$OS" = "Darwin" ]; then
  APP_BUNDLE="$HOME/Applications/Ressy.app"
  mkdir -p "$APP_BUNDLE/Contents/MacOS"
  cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Ressy</string>
  <key>CFBundleIdentifier</key><string>top.ressy.desktop</string>
  <key>CFBundleExecutable</key><string>Ressy</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
  cp "$BIN_DIR/ressy" "$APP_BUNDLE/Contents/MacOS/Ressy"
  chmod +x "$APP_BUNDLE/Contents/MacOS/Ressy"
  echo "macOS app bundle created at $APP_BUNDLE"
else
  DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$DESKTOP_DIR"
  cat > "$DESKTOP_DIR/ressy.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Ressy
Comment=Free AI voice assistant for desktop
Exec=$BIN_DIR/ressy
Terminal=false
Categories=Utility;AudioVideo;
DESKTOP
  echo "Linux desktop launcher created at $DESKTOP_DIR/ressy.desktop"
fi

echo "Done! Run 'ressy' (or make sure $BIN_DIR is in your PATH)."
