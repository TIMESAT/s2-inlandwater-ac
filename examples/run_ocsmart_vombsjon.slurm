#!/usr/bin/env bash
#SBATCH --job-name=ocsmart-vomb
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/projects/eko/fs7/pers/ZC/TWIN_water/ocsmart-%j.log

set -euo pipefail

BASE="${TWIN_WATER_BASE:-/projects/eko/fs7/pers/ZC/TWIN_water}"
APP="${S2_WATER_AC_HOME:-${BASE}/s2-inlandwater-ac}"
DATA="${S2_L1C_DIR:-${BASE}/S2L1C/T33UVB}"
OUT="${S2_AC_OUTPUT:-${BASE}/OCSMART_VOMBSJON}"
OCENV="${OCSMART_ENV:-${APP}/.external/envs/ocsmart}"
RUNNER="${S2_WATER_AC_RUNNER:-${APP}/.venv/bin/s2-water-ac}"

export OCSMART_HOME="${OCSMART_HOME:-${APP}/.external/OC-SMART_Python_Linux_v2.2}"
export OCSMART_PYTHON="${OCSMART_PYTHON:-${OCENV}/bin/python}"
export OCSMART_CACHE="${OCSMART_CACHE:-${BASE}/cache/ocsmart}"

if [[ ! -x "$RUNNER" ]]; then
  echo "Missing s2-water-ac executable: $RUNNER" >&2
  exit 2
fi
if [[ ! -x "$OCSMART_PYTHON" ]]; then
  echo "Missing OC-SMART Python: $OCSMART_PYTHON" >&2
  exit 2
fi
if [[ ! -f "$OCSMART_HOME/OCSMART.py" ]]; then
  echo "Missing OC-SMART launcher: $OCSMART_HOME/OCSMART.py" >&2
  exit 2
fi
if [[ ! -d "$DATA" ]]; then
  echo "Missing Sentinel-2 input directory: $DATA" >&2
  exit 2
fi

mkdir -p "$OUT" "$OCSMART_CACHE"
"$RUNNER" doctor --backend ocsmart

"$RUNNER" batch "$DATA" \
  --backend ocsmart \
  --output "$OUT" \
  --set l2_prod=rrs,chl,tsm
