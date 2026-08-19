#!/usr/bin/env bash
#SBATCH --job-name=acolite-vomb
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=/projects/eko/fs7/pers/ZC/TWIN_water/acolite-%j.log

set -euo pipefail

BASE="${TWIN_WATER_BASE:-/projects/eko/fs7/pers/ZC/TWIN_water}"
APP="${S2_WATER_AC_HOME:-${BASE}/s2-inlandwater-ac}"
DATA="${S2_L1C_DIR:-${BASE}/S2L1C/T33UVB}"
ROI="${VOMBSJON_ROI:-${BASE}/vombsjon.geojson}"
OUT="${S2_AC_OUTPUT:-${BASE}/ACOLITE_VOMBSJON}"
ACENV="${ACOLITE_ENV:-${APP}/.external/envs/acolite}"

export ACOLITE_HOME="${ACOLITE_HOME:-${APP}/.external/acolite}"
export ACOLITE_PYTHON="${ACOLITE_PYTHON:-${ACENV}/bin/python}"

RUNNER="${S2_WATER_AC_RUNNER:-${ACENV}/bin/s2-water-ac}"

if [[ ! -x "$RUNNER" ]]; then
  echo "Missing s2-water-ac executable: $RUNNER" >&2
  exit 2
fi
if [[ ! -f "$ACOLITE_HOME/launch_acolite.py" ]]; then
  echo "Missing ACOLITE launcher: $ACOLITE_HOME/launch_acolite.py" >&2
  exit 2
fi
if [[ ! -d "$DATA" ]]; then
  echo "Missing Sentinel-2 input directory: $DATA" >&2
  exit 2
fi
if [[ ! -f "$ROI" ]]; then
  echo "Missing Vombsjön ROI: $ROI" >&2
  exit 2
fi

mkdir -p "$OUT"

"$RUNNER" batch "$DATA" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$OUT" \
  --set "polygon=$ROI" \
  --set polygon_clip=True \
  --set ancillary_data=False
