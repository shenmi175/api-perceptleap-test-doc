#!/usr/bin/env bash
set -euo pipefail

if [ -t 0 ]; then
  stty -echo
  trap 'stty echo' EXIT
fi

python3 probe_perceptleap.py --key-stdin "$@"
