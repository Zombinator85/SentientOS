#!/usr/bin/env bash
set -euo pipefail
export SENTIENTOS_HEADLESS=${SENTIENTOS_HEADLESS:-1}
export LUMOS_AUTO_APPROVE=${LUMOS_AUTO_APPROVE:-1}
if [[ $# -eq 0 ]]; then
  python sosctl.py rehearse --cycles 1
elif [[ $# -eq 1 && $1 =~ ^[0-9]+$ ]]; then
  python sosctl.py rehearse --cycles "$1"
else
  python sosctl.py rehearse "$@"
fi
