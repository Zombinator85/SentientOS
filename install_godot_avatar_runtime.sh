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
DEMO_SOURCE="$ROOT_DIR/godot_avatar_demo"
DEMO_DIR="$TOOLS_DIR/demo"
LAUNCHER="$TOOLS_DIR/avatar-demo.sh"

mkdir -p "$TOOLS_DIR" "$DATA_ROOT"

STATE_FILE="$DATA_ROOT/avatar_state.json"
echo "[avatar-runtime] Ensuring avatar_state.json is available at $STATE_FILE"
touch "$STATE_FILE"
ln -sf "$STATE_FILE" "$TOOLS_DIR/avatar_state.json"

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

if [ -d "$DEMO_SOURCE" ]; then
  echo "[avatar-runtime] Syncing Godot demo scene"
  rm -rf "$DEMO_DIR"
  mkdir -p "$DEMO_DIR"
  cp -R "$DEMO_SOURCE"/. "$DEMO_DIR"/
  ln -sf "$STATE_FILE" "$DEMO_DIR/avatar_state.json"
else
  echo "[avatar-runtime] Demo source missing at $DEMO_SOURCE"
fi

cat > "$TOOLS_DIR/README.md" <<'RUNTIME'
# Avatar Runtime

The avatar runtime pairs Godot with SentientOS state output.

- `avatar_state.json` is a symlink to the live emitter output.
- `demo/` contains a runnable Godot project with a UDP listener wired to placeholder blendshapes and motions.
- Use `avatar-demo.sh` to run the receiver and open the scene quickly.
RUNTIME

cat > "$LAUNCHER" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/demo"
STATE_FILE="$ROOT_DIR/avatar_state.json"
GODOT_BIN_OVERRIDE=${GODOT_BIN:-}

if command -v godot >/dev/null 2>&1; then
  GODOT_BIN_OVERRIDE=${GODOT_BIN_OVERRIDE:-$(command -v godot)}
fi
GODOT_BIN_PATH=${GODOT_BIN_OVERRIDE:-$ROOT_DIR/godot}

python "$REPO_ROOT/godot_avatar_receiver.py" --state-file "$STATE_FILE" &
RECEIVER_PID=$!
trap 'kill $RECEIVER_PID 2>/dev/null || true' EXIT

exec "$GODOT_BIN_PATH" --path "$PROJECT_DIR" --scene "res://scenes/avatar_demo.tscn"
LAUNCH

chmod +x "$LAUNCHER"

echo "[avatar-runtime] Ready. Launch with $LAUNCHER"
