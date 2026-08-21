# Sentinel-2 内陆水体大气校正统一工具

`s2-water-ac` 为 Sentinel-2 L1C `.SAFE` / `.SAFE.zip` 提供统一的命令行入口。它负责产品校验、批量发现、参数转译、外部进程调用、日志记录和结果清单；大气校正本身仍由经过科研社区使用和验证的官方处理器完成。

## 支持的处理器

| 后端 | 默认策略 | 典型用途 | 输出 |
|---|---|---|---|
| `acolite` | DSF，20 m，生成 `Rrs_*` | 浑浊、富营养化内陆水体；推荐首选 | ACOLITE NetCDF + GeoTIFF |
| `c2rcc` | `C2X-COMPLEX-Nets`，`outputAsRrs=true` | 光学复杂内陆水体，神经网络反演 | SNAP BEAM-DIMAP |
| `ocsmart` | `rrs,chl`，MSI 固定 60 m | 沿海/内陆复杂水体，科学机器学习反演 | HDF5 |
| `polymer` | 20 m，优先读取 SAFE 内嵌 ECMWF | 太阳耀斑明显的水体 | NetCDF |

本项目不捆绑这些外部软件。这样既避免复制数 GB 的 LUT/辅助数据，也保留各处理器各自的许可证、更新方式和可追溯版本。

## 安装统一入口

```bash
cd /Users/zzcai/Documents/GitHub/s2-inlandwater-ac
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/s2-water-ac backends
.venv/bin/s2-water-ac doctor
```

统一入口本身只使用 Python 标准库，支持 Python 3.9 及以上。`doctor` 返回非零表示至少一个外部处理器尚未安装，这是预期的初始状态。

## 外部处理器配置

### ACOLITE

按 [ACOLITE 官方仓库](https://github.com/acolite/acolite) 创建它自己的 Python/conda 环境，然后设置：

```bash
export ACOLITE_HOME=/path/to/acolite
export ACOLITE_PYTHON=/path/to/acolite-environment/bin/python
s2-water-ac doctor --backend acolite
```

也可用 `ACOLITE_LAUNCHER=/path/to/launch_acolite.py`。ACOLITE 首次运行可能联网下载 LUT。

如果 ACOLITE 源码和环境分别安装在项目内的 `.external/acolite` 与
`.external/envs/acolite`，统一入口会自动发现它们，无需每次设置环境变量。
在线 ancillary 数据需要 Earthdata 凭据；没有凭据时 ACOLITE 会退回默认大气参数。
可配置 `.netrc`，或在明确接受默认值时传入 `--set ancillary_data=False`。

### SNAP C2RCC

安装 ESA SNAP 及 Optical Toolbox/C2RCC，并把 `SNAP_GPT` 指向 SNAP Graph Processing Tool：

```bash
export SNAP_GPT=/Applications/snap/bin/gpt
s2-water-ac doctor --backend c2rcc
```

macOS 自带的 `/usr/sbin/gpt` 是磁盘分区程序，不是 SNAP。本工具会明确拒绝它。

### POLYMER

按 [POLYMER 官方仓库](https://github.com/hygeos/polymer) 建立独立环境。推荐设置该环境的 Python，而不是功能有限的 `polymer_cli.py`：

```bash
export POLYMER_PYTHON=/path/to/polymer-environment/bin/python
s2-water-ac doctor --backend polymer
```

本工具的 POLYMER driver 暴露 10/20/60 m 分辨率以及内嵌 ECMWF 辅助数据。若只设置 `POLYMER_CLI`，官方简易 CLI 对 MSI 使用默认 60 m，且不接受高级参数。

### OC-SMART

从 [OC-SMART 官方页面](http://www.rtatmocn.com/oc-smart/) 下载 Linux 包，并按包内
`UserGuide_Python_Linux.pdf` 创建独立 Python 环境。不要把官方程序、神经网络数据或
Earthdata 凭据提交到本仓库；官方许可仅允许非商业科研使用且禁止向第三方转发软件。

```bash
export OCSMART_HOME=/path/to/OC-SMART_Python_Linux_v2.2
export OCSMART_PYTHON=/path/to/ocsmart-environment/bin/python
export OCSMART_CACHE=/path/to/ocsmart-cache  # 可选，批处理时复用 ancillary 数据
s2-water-ac doctor --backend ocsmart
```

OC-SMART 从当前工作目录读取固定名称 `OCSMART_Input.txt`。统一入口会为每景创建隔离的
`.ocsmart-runtime`，不会改写官方安装目录，也不会把输入目录中的其他 SAFE 一起处理。
Sentinel-2 在官方 Linux v2.2 中固定以 60 m 处理，因此本后端忽略 `--resolution`。

## Python 调用方式

四种处理器都可以由 Python 工作流调用，但实现方式不同：

- ACOLITE 是原生 Python。官方入口 `acolite_run` 接受 settings 文件或字典；本工具通过其独立 Python 环境启动 `launch_acolite.py`，避免 GDAL、NetCDF 等依赖污染当前项目环境。
- POLYMER 是 Python/Cython。`polymer_driver.py` 直接调用官方 `run_atm_corr(Level1(...), Level2(...))`，同时暴露 MSI 分辨率、辅助数据和多进程参数。
- C2RCC 是 SNAP 的 Java GPF Operator，不是纯 Python 包。本工具从 Python 用参数数组启动 SNAP `gpt c2rcc.msi`。SNAP 12+ 也提供 `esa_snappy.GPF.createProduct()`，但它仍依赖完整 SNAP/JVM；批处理时 `gpt` 的进程隔离通常更容易复现和排错。
- OC-SMART 是独立 Python 程序。统一入口生成官方格式的 `OCSMART_Input.txt`，并在其专用环境中启动 `OCSMART.py`；官方源码和辅助数据仍留在外部安装目录。

因此，用户侧只需要调用本项目的 Python API/CLI，不需要手动编写 shell 脚本；各算法仍建议保留独立运行环境。

## 使用样例数据

先校验一个产品：

```bash
DATA=/Users/zzcai/Documents/GitHub/s2-l1c-downloader/data/raw/S2_L1C/T33UVB
PRODUCT="$DATA/S2A_MSIL1C_20210728T103031_N0500_R108_T33UVB_20230127T023918.SAFE"

s2-water-ac inspect "$PRODUCT"
```

运行 ACOLITE：

```bash
s2-water-ac run "$PRODUCT" \
  --backend acolite \
  --output ./outputs \
  --profile inland \
  --resolution 20
```

运行 C2RCC，并覆盖后端参数：

```bash
s2-water-ac run "$PRODUCT" \
  --backend c2rcc \
  --output ./outputs \
  --set polygon=/path/to/roi.geojson \
  --set polygon_clip=true \
  --set netSet=C2X-COMPLEX-Nets \
  --set outputUncertainties=true
```

C2RCC 先在完整 L1C 产品上执行，再将结果裁到 GeoJSON 的外接范围，避免预裁剪破坏
处理器依赖的 Sentinel-2 元数据。精确的多边形像元掩膜应在标准化或统计阶段应用。

运行 POLYMER：

```bash
s2-water-ac run "$PRODUCT" \
  --backend polymer \
  --output ./outputs \
  --resolution 20 \
  --set ancillary=embedded \
  --set multiprocessing=-1
```

`ancillary=embedded` 使用 SAFE 中的 `AUX_ECMWFT`，无需 NASA Earthdata 登录；可改为 `ancillary=nasa` 使用 POLYMER 的 NASA 辅助数据流程。

运行 OC-SMART：

```bash
s2-water-ac run "$PRODUCT" \
  --backend ocsmart \
  --output ./outputs \
  --set l2_prod=rrs,chl,tsm
```

OC-SMART 下载 NASA OB.DAAC 辅助数据前，需要按官方用户指南配置 Earthdata 授权。
登录信息只能放在权限为 `0600` 的用户级认证文件中，不能写入命令、配置示例或 Git。

## 批处理

下载目录同时含 `.SAFE` 和同名 `.SAFE.zip` 时，本工具会自动去重并优先使用已解压目录：

```bash
s2-water-ac batch \
  /Users/zzcai/Documents/GitHub/s2-l1c-downloader/data/raw/S2_L1C/T33UVB \
  --backend acolite \
  --output ./outputs \
  --resolution 20
```

默认单个产品失败后继续，并在最后输出 JSON 汇总。添加 `--fail-fast` 可在首次失败时停止。

## Linux/HPC 上处理 Vombsjön 全部影像

Linux 服务器上的示例数据目录为：

```text
/projects/eko/fs7/pers/ZC/TWIN_water/S2L1C/T33UVB
```

macOS 创建的 Python/conda 环境不能直接复制到 Linux；需要在 Linux 上重新创建
ACOLITE 环境。完整步骤（包括 ROI 上传、安装、单景验证、全量批处理和断点续跑）见
[`docs/linux-hpc.md`](docs/linux-hpc.md)。仓库同时提供可直接提交的 Slurm 示例：
[`examples/run_acolite_vombsjon.slurm`](examples/run_acolite_vombsjon.slurm)。

SNAP C2RCC 和 OC-SMART 的 Linux/HPC 安装、单景验证及 Slurm 示例见
[`docs/linux-c2rcc-ocsmart.md`](docs/linux-c2rcc-ocsmart.md)。

环境准备完成后，可直接运行：

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

已有成功 `run.json` 的产品会自动跳过，因此任务中断后可安全地再次运行同一命令。
不要为断点续跑添加 `--force`。

## 预演与结果结构

`--dry-run` 校验产品和参数并打印完整命令，但不创建输出目录：

```bash
s2-water-ac run "$PRODUCT" --backend acolite --output ./outputs --dry-run
```

每个结果使用独立目录：

```text
outputs/
└── <product-id>/
    └── <backend>/
        ├── run.json              # 参数、完整 argv、时间、状态和预期输出
        ├── run.log               # 合并后的 stdout/stderr
        ├── acolite-settings.txt  # 仅 ACOLITE
        ├── .ocsmart-runtime/     # 仅 OC-SMART；隔离配置、输入链接和缓存入口
        └── ...算法结果...
```

已有成功 `run.json` 时会安全跳过。`--force` 允许处理器重新写入该目录，但不会自动删除任何旧结果。

## 参数约定

- `--set KEY=VALUE` 可重复。ACOLITE 参数原样写入 settings；C2RCC 参数转为 SNAP `-PKEY=VALUE`。
- POLYMER 当前支持 `ancillary`、`multiprocessing`、`blocksize`、`sline`、`eline`、`scol`、`ecol`、`altitude` 和 `use_srf`。
- OC-SMART 支持官方输入项 `l2_prod`、角度限制、三种子区域参数和 `block_size`；`l1b_path`/`l2_path` 由统一入口管理，不能覆盖。
- `--resolution` 作用于 ACOLITE 和 POLYMER。C2RCC 的输出网格由 SNAP/C2RCC 产品定义；OC-SMART v2.2 的 MSI 输出固定为 60 m。
- `.SAFE.zip` 可直接交给 ACOLITE/C2RCC；POLYMER 和 OC-SMART 运行时会安全解压到临时目录并在结束后清理。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -v
```

测试使用微型伪 SAFE 和模拟外部进程，不下载 LUT，也不执行实际大气校正。真实处理前应先运行 `doctor`，再用一个产品做完整验证。

## 科研使用提醒

不同算法输出量纲和归一化约定并不完全相同。ACOLITE 的 `Rrs`、C2RCC 的 `outputAsRrs`、OC-SMART 的 normalized `Rrs` 与 POLYMER 的归一化水体反射率在做像元级比较前，仍应检查变量属性、质量标志、波长对应关系和单位。算法选择应通过研究区现场光谱/水质数据验证，而不是仅凭视觉效果决定。
