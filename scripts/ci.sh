#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO_ROOT"

python3 tools/bootstrap_secondary.py --quiet

# Allow optional developer dependencies without failing the job if the file is missing.
if [[ -f requirements-dev.txt ]]; then
  python3 -m pip install -r requirements-dev.txt || true
fi

cmake -S SentientOSsecondary/llama.cpp/examples/server -B build/examples/server -G Ninja
cmake --build build/examples/server -j

# Run the server binary in a non-interactive way to confirm it links correctly.
./build/examples/server/llama-server --help > build/examples/server/llama-server-help.txt

echo "llama-server --help output preview:" >&2
head -n 20 build/examples/server/llama-server-help.txt >&2

if command -v file >/dev/null 2>&1; then
  file build/examples/server/llama-server
else
  echo "(file command unavailable; skipping binary type inspection)"
fi
if command -v strings >/dev/null 2>&1; then
  strings build/examples/server/llama-server > build/examples/server/llama-server.strings
  if grep -q "/assets/app.js" build/examples/server/llama-server.strings; then
    echo "Verified embedded asset reference present in binary."
  else
    echo "ERROR: Embedded asset reference '/assets/app.js' missing from binary." >&2
    tail -n 20 build/examples/server/llama-server.strings >&2
    exit 1
  fi
else
  echo "(strings command unavailable; skipping manifest string check)"
fi

python3 - <<'PY'
from pathlib import Path

manifest = Path("build/examples/server/static_asset_manifest.hpp")
print("Embedded asset manifest preview:\n")
print("\n".join(line.rstrip() for line in manifest.read_text().splitlines()[:20]))
PY
