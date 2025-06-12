#!/usr/bin/env bash
set -euo pipefail

remote_url=$(git remote get-url origin 2>/dev/null || true)
if [[ -z "$remote_url" || ! "$remote_url" =~ ^git@github.com:.+/.+\.git$ ]]; then
  echo "Remote 'origin' missing or not a GitHub SSH URL." >&2
  echo "Run: git remote add origin git@github.com:<user>/<repo>.git" >&2
  exit 1
fi

git fetch origin
git push origin main
git tag -a "$TAG" -m "$MSG"
git push origin "$TAG"

repo_path=${remote_url#git@github.com:}
repo_path=${repo_path%.git}
echo "https://github.com/$repo_path/releases/tag/$TAG"
