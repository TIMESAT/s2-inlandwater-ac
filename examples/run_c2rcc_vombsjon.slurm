#!/usr/bin/env bash
#SBATCH --job-name=c2rcc-vomb
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=/projects/eko/fs7/pers/ZC/TWIN_water/c2rcc-%j.log

set -euo pipefail

BASE="${TWIN_WATER_BASE:-/projects/eko/fs7/pers/ZC/TWIN_water}"
APP="${S2_WATER_AC_HOME:-${BASE}/s2-inlandwater-ac}"
DATA="${S2_L1C_DIR:-${BASE}/S2L1C/T33UVB}"
OUT="${S2_AC_OUTPUT:-${BASE}/C2RCC_VOMBSJON}"
ROI="${S2_AC_ROI:-${BASE}/vombsjon.geojson}"
RUNNER="${S2_WATER_AC_RUNNER:-${APP}/.venv/bin/s2-water-ac}"

export SNAP_HOME="${SNAP_HOME:-${BASE}/apps/esa-snap-10}"
export SNAP_GPT="${SNAP_GPT:-${SNAP_HOME}/bin/gpt}"

if [[ ! -x "$RUNNER" ]]; then
  echo "Missing s2-water-ac executable: $RUNNER" >&2
  exit 2
fi
if [[ ! -x "$SNAP_GPT" ]]; then
  echo "Missing SNAP GPT executable: $SNAP_GPT" >&2
  exit 2
fi
if [[ ! -d "$DATA" ]]; then
  echo "Missing Sentinel-2 input directory: $DATA" >&2
  exit 2
fi
if [[ ! -f "$ROI" ]]; then
  echo "Missing ROI GeoJSON: $ROI" >&2
  exit 2
fi

"$SNAP_GPT" c2rcc.msi -h >/dev/null
mkdir -p "$OUT"

"$RUNNER" batch "$DATA" \
  --backend c2rcc \
  --profile inland \
  --output "$OUT" \
  --set "polygon=${ROI}" \
  --set polygon_clip=true
