#!/usr/bin/env bash
set -euo pipefail

git fetch origin
git push origin main
git tag -a "$TAG" -m "$MSG"
git push origin "$TAG"
