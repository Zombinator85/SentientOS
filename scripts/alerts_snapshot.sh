#!/usr/bin/env bash
set -euo pipefail
python -m sentientos.alerts snapshot "$@"
python -m sentientos.alerts gauges "$@"
