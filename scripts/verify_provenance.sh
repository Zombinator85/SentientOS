#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST="$REPO_ROOT/glow/releases/v1.0.0/release_manifest_v1.0.0.json"
SIG_FILE="$REPO_ROOT/glow/releases/v1.0.0/release_manifest_v1.0.0.sig"
PUBKEY_FILE="$REPO_ROOT/glow/releases/v1.0.0/codex_release_public.asc"

if [[ ! -f "$MANIFEST" ]]; then
  echo "Release manifest not found at $MANIFEST" >&2
  exit 1
fi

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

python3 - <<'PY' "$MANIFEST" "$workdir/release_manifest_v1.0.0.json" "$REPO_ROOT"
import json
import hashlib
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
sha_file = Path(sys.argv[2])
repo_root = Path(sys.argv[3])

data = json.loads(manifest_path.read_text())
lines = []
for artifact in data.get("artifacts", []):
    path = repo_root / artifact["path"]
    if not path.exists():
        raise SystemExit(f"Artifact missing: {path}")
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    sha512 = hashlib.sha512(path.read_bytes()).hexdigest()
    if sha256 != artifact["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for {path} (expected {artifact['sha256']}, computed {sha256})")
    if sha512 != artifact["sha512"]:
        raise SystemExit(f"SHA-512 mismatch for {path} (expected {artifact['sha512']}, computed {sha512})")
    rel_path = path.relative_to(repo_root)
    lines.append(f"{sha256}  {rel_path}")

sha_file.write_text("\n".join(lines) + "\n")
PY

( cd "$REPO_ROOT" && sha256sum -c "$workdir/release_manifest_v1.0.0.json" )

if command -v gpg >/dev/null 2>&1 && [[ -f "$SIG_FILE" ]]; then
  if [[ -f "$PUBKEY_FILE" ]]; then
    gpg --import --quiet "$PUBKEY_FILE" || true
  fi
  gpg --verify "$SIG_FILE" "$MANIFEST"
fi

echo "All v1.0.0 artifacts verified OK."
