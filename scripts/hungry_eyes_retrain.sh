#!/usr/bin/env bash
set -euo pipefail
export SENTIENTOS_HEADLESS=${SENTIENTOS_HEADLESS:-1}
export LUMOS_AUTO_APPROVE=${LUMOS_AUTO_APPROVE:-1}
python sosctl.py hungry-eyes retrain
