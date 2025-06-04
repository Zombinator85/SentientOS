#!/usr/bin/env bash
# Testing quickstart environment
export MEMORY_DIR=${MEMORY_DIR:-$(pwd)/tmp_memory}
export AVATAR_DIR=${AVATAR_DIR:-$(pwd)/tmp_avatars}
mkdir -p "$MEMORY_DIR" "$AVATAR_DIR"
echo "Environment ready: MEMORY_DIR=$MEMORY_DIR AVATAR_DIR=$AVATAR_DIR"
python installer/setup_installer.py "$@"
