#!/bin/bash
# pull_cathedral.sh
# Description: Synchronizes local SentientOS working branch with upstream main
# Author: Allen Brummitt (initiated)
# Blessing: Codified for those who come after

set -e  # Stop on error

# 🕯️ Announce invocation
echo "~@ Initiating Cathedral Pull Ritual..."

# 📍 Navigate to script root, then into /api
cd "$(dirname "$0")/../api" || {
  echo "✖️ Failed to enter /api directory." >&2
  exit 1
}

# 🧾 Report location
echo "📂 Current directory: $(pwd)"

# 🔁 Refresh from upstream main

echo "🔄 Switching to main..."
git checkout main

echo "📡 Pulling latest from origin/main..."
git pull origin main

# 🌱 Switch back to working branch
WORKING_BRANCH="feat/launcher-gui"
echo "🌿 Switching to $WORKING_BRANCH..."
git checkout "$WORKING_BRANCH"

# 🔀 Merge changes in

echo "🧬 Merging main into $WORKING_BRANCH..."
git merge main

# ✅ Finish
if [ $? -eq 0 ]; then
  echo "~@ Cathedral code is now synchronized and blessed."
else
  echo "✖️ Merge failed. Manual resolution required." >&2
  exit 1
fi
