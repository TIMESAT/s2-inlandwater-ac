# Unified Atmospheric Correction Tool for Sentinel-2 Inland Waters

`s2-water-ac` provides a unified command-line interface for Sentinel-2 L1C `.SAFE` and `.SAFE.zip` products. It handles product validation, batch discovery, parameter translation, external process invocation, logging, and result manifests. Atmospheric correction itself is still performed by established processors used and validated by the scientific community.

## Supported Processors

| Backend | Default configuration | Typical use | Output |
|---|---|---|---|
| `acolite` | DSF, 20 m, generates `Rrs_*` | Turbid and eutrophic inland waters; recommended first choice | ACOLITE NetCDF + GeoTIFF |
| `c2rcc` | 20 m, `C2X-COMPLEX-Nets`, `outputAsRrs=true` | Optically complex inland waters; neural-network retrieval | SNAP BEAM-DIMAP |
| `ocsmart` | `rrs,chl`, fixed 60 m for MSI | Complex coastal and inland waters; scientific machine-learning retrieval | HDF5 |
| `polymer` | 20 m, prefers ECMWF data embedded in the SAFE product | Waters affected by strong sun glint | NetCDF |

This project does not bundle these external applications. This avoids duplicating several gigabytes of lookup tables and auxiliary data while preserving each processor's own licensing, update process, and traceable version history.

## Install the Unified Interface

```bash
cd /Users/zzcai/Documents/GitHub/s2-inlandwater-ac
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/s2-water-ac backends
.venv/bin/s2-water-ac doctor
```

The unified interface itself uses only the Python standard library and supports Python 3.9 or later. A nonzero exit status from `doctor` means that at least one external processor has not yet been installed, which is expected during initial setup.

## Configure External Processors

### ACOLITE

Create a dedicated Python or conda environment as described in the [official ACOLITE repository](https://github.com/acolite/acolite), then set:

```bash
export ACOLITE_HOME=/path/to/acolite
export ACOLITE_PYTHON=/path/to/acolite-environment/bin/python
s2-water-ac doctor --backend acolite
```

You may alternatively set `ACOLITE_LAUNCHER=/path/to/launch_acolite.py`. ACOLITE may download lookup tables from the internet on its first run.

If the ACOLITE source and environment are installed inside the project at `.external/acolite` and `.external/envs/acolite`, respectively, the unified interface discovers them automatically, so the environment variables do not need to be set each time. Online ancillary data requires Earthdata credentials. Without credentials, ACOLITE falls back to default atmospheric parameters. Configure `.netrc`, or pass `--set ancillary_data=False` when explicitly accepting the defaults.

### SNAP C2RCC

Install ESA SNAP with the Optical Toolbox and C2RCC, then point `SNAP_GPT` to the SNAP Graph Processing Tool:

```bash
export SNAP_GPT=/Applications/snap/bin/gpt
s2-water-ac doctor --backend c2rcc
```

The `/usr/sbin/gpt` program included with macOS is a disk-partitioning utility, not SNAP. This tool explicitly rejects it.

### POLYMER

Create a dedicated environment following the [official POLYMER repository](https://github.com/hygeos/polymer). Setting the Python interpreter for that environment is recommended instead of using the more limited `polymer_cli.py`:

```bash
export POLYMER_PYTHON=/path/to/polymer-environment/bin/python
s2-water-ac doctor --backend polymer
```

The POLYMER driver included with this tool exposes 10, 20, and 60 m resolutions, as well as embedded ECMWF ancillary data. If only `POLYMER_CLI` is set, the basic official CLI uses the default 60 m resolution for MSI and does not accept advanced parameters.

### OC-SMART

Download the Linux package from the [official OC-SMART website](http://www.rtatmocn.com/oc-smart/) and create a dedicated Python environment by following the included `UserGuide_Python_Linux.pdf`. Do not commit the official application, neural-network data, or Earthdata credentials to this repository. The official license permits noncommercial scientific research only and prohibits redistribution of the software to third parties.

```bash
export OCSMART_HOME=/path/to/OC-SMART_Python_Linux_v2.2
export OCSMART_PYTHON=/path/to/ocsmart-environment/bin/python
export OCSMART_CACHE=/path/to/ocsmart-cache  # Optional: reuse ancillary data during batch processing
s2-water-ac doctor --backend ocsmart
```

OC-SMART reads a fixed file named `OCSMART_Input.txt` from the current working directory. The unified interface creates an isolated `.ocsmart-runtime` for each scene. It neither modifies the official installation directory nor processes other SAFE products from the input directory. Sentinel-2 is always processed at 60 m by the official Linux v2.2 release, so this backend ignores `--resolution`.

## Python Integration

All four processors can be invoked from Python workflows, although their implementations differ:

- ACOLITE is native Python. Its official `acolite_run` entry point accepts a settings file or dictionary. This tool launches `launch_acolite.py` through ACOLITE's isolated Python environment to prevent dependencies such as GDAL and NetCDF from affecting the current project environment.
- POLYMER uses Python and Cython. `polymer_driver.py` directly calls the official `run_atm_corr(Level1(...), Level2(...))` API while exposing MSI resolution, ancillary-data, and multiprocessing options.
- C2RCC is a SNAP Java GPF operator rather than a pure Python package. This tool uses Python to launch SNAP as `gpt c2rcc.msi` with an argument array. SNAP 12 and later also provide `esa_snappy.GPF.createProduct()`, but this still requires a complete SNAP/JVM installation. For batch processing, the process isolation provided by `gpt` is usually easier to reproduce and troubleshoot.
- OC-SMART is a standalone Python application. The unified interface generates an official-format `OCSMART_Input.txt` and launches `OCSMART.py` in its dedicated environment. The official source code and auxiliary data remain in the external installation directory.

Users therefore only need to call this project's Python API or CLI and do not have to write shell scripts manually. Keeping each algorithm in a separate runtime environment is still recommended.

## Use the Sample Data

First, validate a product:

```bash
DATA=/Users/zzcai/Documents/GitHub/s2-l1c-downloader/data/raw/S2_L1C/T33UVB
PRODUCT="$DATA/S2A_MSIL1C_20210728T103031_N0500_R108_T33UVB_20230127T023918.SAFE"

s2-water-ac inspect "$PRODUCT"
```

Run ACOLITE:

```bash
s2-water-ac run "$PRODUCT" \
  --backend acolite \
  --output ./outputs \
  --profile inland \
  --resolution 20
```

Run C2RCC and override backend parameters:

```bash
s2-water-ac run "$PRODUCT" \
  --backend c2rcc \
  --output ./outputs \
  --resolution 20 \
  --set polygon=/path/to/roi.geojson \
  --set polygon_clip=true \
  --set netSet=C2X-COMPLEX-Nets \
  --set outputUncertainties=true
```

The C2RCC graph first uses the official `S2Resampling` operator to resample the multiresolution L1C product to the specified resolution. It then crops the product to the GeoJSON bounding extent and runs C2RCC only within that area, avoiding processing of the complete Sentinel-2 tile. Apply the exact polygon pixel mask during standardization or statistical analysis.

Run POLYMER:

```bash
s2-water-ac run "$PRODUCT" \
  --backend polymer \
  --output ./outputs \
  --resolution 20 \
  --set ancillary=embedded \
  --set multiprocessing=-1
```

`ancillary=embedded` uses `AUX_ECMWFT` from the SAFE product and does not require a NASA Earthdata login. Set `ancillary=nasa` instead to use POLYMER's NASA ancillary-data workflow.

Run OC-SMART:

```bash
s2-water-ac run "$PRODUCT" \
  --backend ocsmart \
  --output ./outputs \
  --set l2_prod=rrs,chl,tsm
```

Before OC-SMART can download NASA OB.DAAC ancillary data, configure Earthdata authorization according to the official user guide. Login information must be stored only in a user-level credential file with `0600` permissions; never include it in commands, configuration examples, or Git.

## Batch Processing

When a download directory contains both a `.SAFE` directory and a matching `.SAFE.zip` archive, this tool automatically deduplicates them and prefers the extracted directory:

```bash
s2-water-ac batch \
  /Users/zzcai/Documents/GitHub/s2-l1c-downloader/data/raw/S2_L1C/T33UVB \
  --backend acolite \
  --output ./outputs \
  --resolution 20
```

By default, processing continues when an individual product fails and prints a JSON summary at the end. Add `--fail-fast` to stop after the first failure.

## Process All Vombsjön Images on Linux/HPC

The example data directory on the Linux server is:

```text
/projects/eko/fs7/pers/ZC/TWIN_water/S2L1C/T33UVB
```

Python and conda environments created on macOS cannot be copied directly to Linux; recreate the ACOLITE environment on Linux. See [`docs/linux-hpc.md`](docs/linux-hpc.md) for the complete procedure, including ROI upload, installation, single-scene validation, full batch processing, and resuming interrupted runs. The repository also includes a ready-to-submit Slurm example: [`examples/run_acolite_vombsjon.slurm`](examples/run_acolite_vombsjon.slurm).

For Linux/HPC installation, single-scene validation, and Slurm examples for SNAP C2RCC and OC-SMART, see [`docs/linux-c2rcc-ocsmart.md`](docs/linux-c2rcc-ocsmart.md).

Once the environment is ready, run:

```bash
BASE=/projects/eko/fs7/pers/ZC/TWIN_water
APP="$BASE/s2-inlandwater-ac"
ACENV="$APP/.external/envs/acolite"

export ACOLITE_HOME="$APP/.external/acolite"
export ACOLITE_PYTHON="$ACENV/bin/python"

"$ACENV/bin/s2-water-ac" batch "$BASE/S2L1C/T33UVB" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$BASE/ACOLITE_VOMBSJON" \
  --set "polygon=$BASE/vombsjon.geojson" \
  --set polygon_clip=True \
  --set ancillary_data=False
```

Products with an existing successful `run.json` are skipped automatically, so the same command can be run safely after an interruption. Do not add `--force` when resuming a run.

## Dry Runs and Result Structure

`--dry-run` validates the product and parameters and prints the complete command without creating an output directory:

```bash
s2-water-ac run "$PRODUCT" --backend acolite --output ./outputs --dry-run
```

Each result is stored in a separate directory:

```text
outputs/
└── <product-id>/
    └── <backend>/
        ├── run.json              # Parameters, complete argv, timestamps, status, and expected outputs
        ├── run.log               # Combined stdout and stderr
        ├── acolite-settings.txt  # ACOLITE only
        ├── .ocsmart-runtime/     # OC-SMART only: isolated config, input link, and cache entry point
        └── ...algorithm outputs...
```

Processing is safely skipped when a successful `run.json` already exists. `--force` allows the processor to write to that directory again but does not automatically delete any old results.

## Parameter Conventions

- `--set KEY=VALUE` may be specified multiple times. ACOLITE parameters are written unchanged to its settings file, while C2RCC parameters are written to a traceable SNAP graph XML file.
- POLYMER currently supports `ancillary`, `multiprocessing`, `blocksize`, `sline`, `eline`, `scol`, `ecol`, `altitude`, and `use_srf`.
- OC-SMART supports the official `l2_prod` input, angle limits, three subregion parameters, and `block_size`. The unified interface manages `l1b_path` and `l2_path`, so they cannot be overridden.
- `--resolution` applies to ACOLITE, C2RCC's `S2Resampling`, and POLYMER. OC-SMART v2.2 produces fixed 60 m MSI output.
- `.SAFE.zip` files may be passed directly to ACOLITE and C2RCC. For POLYMER and OC-SMART, they are securely extracted to a temporary directory and cleaned up after processing.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -v
```

The tests use miniature mock SAFE products and simulated external processes. They do not download lookup tables or perform actual atmospheric correction. Before processing real data, run `doctor`, then validate the complete workflow with a single product.

## Notes for Scientific Use

The output units and normalization conventions are not identical across algorithms. Before comparing pixels, check the variable attributes, quality flags, wavelength mappings, and units for ACOLITE `Rrs`, C2RCC `outputAsRrs`, OC-SMART normalized `Rrs`, and POLYMER normalized water reflectance. Algorithm selection should be validated against in situ spectral or water-quality measurements from the study area rather than based solely on visual appearance.
