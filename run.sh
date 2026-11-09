#!/usr/bin/env bash
# Contract: ./run.sh <SIM_URL> runs the controller until the scenario finishes. No manual steps.
# Plain Python with the packages in requirements.txt; fine on a 4 vCPU / 8 GB Linux box, no Docker needed.
set -euo pipefail
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
cd "$(dirname "$0")"
exec python -m controller.loop --url "$SIM_URL" --db "${CONTROLLER_DB:-data/controller.db}"