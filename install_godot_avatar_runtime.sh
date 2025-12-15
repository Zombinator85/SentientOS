#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
TOOLS_DIR="$ROOT_DIR/tools/avatar_runtime"
DATA_ROOT=${SENTIENTOS_DATA_DIR:-"$ROOT_DIR/sentientos_data"}
GODOT_VERSION=${GODOT_VERSION:-"4.3"}
GODOT_FLAVOR=${GODOT_FLAVOR:-"stable"}
GODOT_ARCHIVE="Godot_v${GODOT_VERSION}-${GODOT_FLAVOR}_linux.x86_64.zip"
GODOT_URL="https://downloads.tuxfamily.org/godotengine/${GODOT_VERSION}/${GODOT_ARCHIVE}"
GODOT_BIN="$TOOLS_DIR/godot"

mkdir -p "$TOOLS_DIR" "$DATA_ROOT"

echo "[avatar-runtime] Ensuring avatar_state.json is available"
touch "$DATA_ROOT/avatar_state.json"
ln -sf "$DATA_ROOT/avatar_state.json" "$TOOLS_DIR/avatar_state.json"

command -v godot >/dev/null 2>&1 && GODOT_BIN="$(command -v godot)"

if [ ! -x "$GODOT_BIN" ]; then
  echo "[avatar-runtime] Downloading Godot $GODOT_VERSION..."
  curl -L "$GODOT_URL" -o "$TOOLS_DIR/godot.zip"
  unzip -o "$TOOLS_DIR/godot.zip" -d "$TOOLS_DIR" >/dev/null
  mv "$TOOLS_DIR/Godot_v${GODOT_VERSION}-${GODOT_FLAVOR}_linux.x86_64" "$GODOT_BIN"
  chmod +x "$GODOT_BIN"
  rm -f "$TOOLS_DIR/godot.zip"
else
  echo "[avatar-runtime] Reusing existing Godot binary at $GODOT_BIN"
fi

DEMO_DIR="$TOOLS_DIR/demo"
mkdir -p "$DEMO_DIR"
cat > "$DEMO_DIR/avatar_demo_scene.md" <<'EOF'
# Avatar Demo Scene

This placeholder documents the expected Godot scene layout.
Load a VRM-compatible avatar into the scene and connect a script that reads
`../avatar_state.json` to drive blendshapes and idle motions.
EOF

cat > "$TOOLS_DIR/README.md" <<'EOF'
# Avatar Runtime

The avatar runtime pairs Godot with SentientOS state output.
- `avatar_state.json` is a symlink to the live emitter output.
- `demo/avatar_demo_scene.md` describes the minimal Godot setup for VRM avatars.
EOF

echo "[avatar-runtime] Ready. Launch Godot with $GODOT_BIN --editor $DEMO_DIR to link your avatar." 
