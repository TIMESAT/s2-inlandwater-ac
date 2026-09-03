#!/usr/bin/env bash
#SBATCH --job-name=acolite-erken
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=/projects/eko/fs7/pers/ZC/TWIN_water/acolite-erken-%j.log

set -euo pipefail

BASE="${TWIN_WATER_BASE:-/projects/eko/fs7/pers/ZC/TWIN_water}"
APP="${S2_WATER_AC_HOME:-${BASE}/s2-inlandwater-ac}"
DATA="${S2_L1C_DIR:-${BASE}/S2L1C/T34VCM}"
ROI="${ERKEN_ROI:-${APP}/examples/erken-processing-roi-5km.geojson}"
OUT="${S2_AC_OUTPUT:-${BASE}/ACOLITE_ERKEN}"
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
  echo "Missing Erken Sentinel-2 L1C input directory: $DATA" >&2
  exit 2
fi
if [[ ! -f "$ROI" ]]; then
  echo "Missing Erken ROI: $ROI" >&2
  exit 2
fi

"$ACOLITE_PYTHON" - "$ROI" <<'PY'
import sys
from osgeo import ogr

path = sys.argv[1]
dataset = ogr.Open(path)
if dataset is None:
    raise SystemExit("Invalid or unreadable Erken ROI: {}".format(path))
layer = dataset.GetLayer()
if layer is None or layer.GetFeatureCount() != 1:
    raise SystemExit("Erken ROI must contain exactly one polygon feature: {}".format(path))
feature = layer.GetNextFeature()
geometry = feature.GetGeometryRef() if feature is not None else None
if geometry is None or geometry.GetGeometryName() not in {"POLYGON", "MULTIPOLYGON"}:
    raise SystemExit("Erken ROI feature is not a polygon: {}".format(path))
if not geometry.IsValid():
    raise SystemExit("Erken ROI polygon is invalid: {}".format(path))
print("Validated Erken ROI: {} ({})".format(path, geometry.GetGeometryName()))
PY

mkdir -p "$OUT"

"$RUNNER" batch "$DATA" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$OUT" \
  --set "polygon=$ROI" \
  --set polygon_clip=True \
  --set ancillary_data=False
