# Linux/HPC 上运行 C2RCC 与 OC-SMART

本文沿用项目的默认服务器目录：

```bash
export BASE=/projects/eko/fs7/pers/ZC/TWIN_water
export APP="$BASE/s2-inlandwater-ac"
export DATA="$BASE/S2L1C/T33UVB"
export RUNNER="$APP/.venv/bin/s2-water-ac"
```

统一入口、SNAP 和 OC-SMART 必须分开安装。仓库只保存调用适配、日志和结果清单，
不保存第三方处理器、Sentinel-2 输入、辅助数据或算法输出。

## 1. 安装统一入口

```bash
cd "$APP"
python3 -m venv .venv
"$APP/.venv/bin/python" -m pip install -e "$APP"
"$RUNNER" backends
```

现有 ACOLITE/POLYMER 命令和输出目录不变。新增后端只会在选择 `--backend ocsmart`
时创建 `.ocsmart-runtime` 子目录。

## 2. SNAP C2RCC

### 2.1 安装与检查

从 [ESA SNAP 下载页](https://step.esa.int/main/download/snap-download/) 获取 Linux
Sentinel Toolboxes 或 All Toolboxes 安装器。官方也支持在无图形界面的登录节点使用
console 模式：

```bash
chmod +x /path/to/esa-snap-installer.sh
/path/to/esa-snap-installer.sh -c
```

安装时必须包含 Optical/Sentinel-3 Toolbox，因为 `c2rcc.msi` 由相关模块提供。设置：

```bash
export SNAP_HOME="$BASE/apps/esa-snap-10"
export SNAP_GPT="$SNAP_HOME/bin/gpt"

"$SNAP_GPT" -h
"$SNAP_GPT" c2rcc.msi -h
"$RUNNER" doctor --backend c2rcc
```

最后两项检查含义不同：`doctor` 检查 GPT 路径；`gpt c2rcc.msi -h` 检查处理器
是否真正注册。如果出现 `SPI not found for operator 'c2rcc.msi'`，应回到 SNAP
安装器/Plugin Manager 补装或更新 Optical/Sentinel-3 Toolbox，而不是修改本项目代码。

### 2.2 单景验证

```bash
PRODUCT=$(find "$DATA" -maxdepth 1 -type d -name '*.SAFE' | sort | head -n 1)

"$RUNNER" run "$PRODUCT" \
  --backend c2rcc \
  --profile inland \
  --output "$BASE/C2RCC_VOMBSJON" \
  --set "polygon=$BASE/vombsjon.geojson" \
  --set polygon_clip=true
```

`inland` 默认使用 `C2X-COMPLEX-Nets`、`outputAsRrs=true` 和
`outputUncertainties=true`。结果保留为 BEAM-DIMAP（`.dim` + `.data/`），避免部分
SNAP/NetCDF 组合在大型元数据产品上出现原生崩溃。

为避免预裁剪破坏 C2RCC 所依赖的 Sentinel-2 L1C 元数据，带 `polygon` 时统一入口先在
原始产品上运行 C2RCC，再用同一个 GeoJSON 将结果裁到 ROI 的外接范围。SNAP 原生栅格
仍为矩形；多边形外的像元在后续标准化或统计阶段使用同一 GeoJSON 精确掩膜。生成的
`c2rcc-roi.xml` 会随 `run.json` 一起保留，记录实际处理顺序和 WKT 区域。

### 2.3 批处理与 Slurm

```bash
"$RUNNER" batch "$DATA" \
  --backend c2rcc \
  --profile inland \
  --output "$BASE/C2RCC_VOMBSJON" \
  --set "polygon=$BASE/vombsjon.geojson" \
  --set polygon_clip=true
```

也可直接提交仓库示例：

```bash
cd "$APP"
sbatch examples/run_c2rcc_vombsjon.slurm
```

## 3. OC-SMART Linux v2.2

### 3.1 许可边界

OC-SMART 官方 v2.2 用户指南授予个人、非独占、不可转让的非商业科研许可，并禁止
向第三方转发原版或修改版软件。因此每位有权使用的研究人员应从
[OC-SMART 官方页面](http://www.rtatmocn.com/oc-smart/) 自行下载；本仓库和容器镜像
不得捆绑它的源码、神经网络、`auxdata` 或用户认证文件。

### 3.2 安装独立环境

```bash
mkdir -p "$APP/.external/envs"
cd "$APP/.external"
curl -LO http://www.rtatmocn.com/oc-smart/OC-SMART_Python_Linux_v2.2.zip
unzip OC-SMART_Python_Linux_v2.2.zip

export OCSMART_HOME="$APP/.external/OC-SMART_Python_Linux_v2.2"
export OCSMART_ENV="$APP/.external/envs/ocsmart"

conda create -y --prefix "$OCSMART_ENV" python=3.11.4
conda install -y --prefix "$OCSMART_ENV" \
  numpy gdal scipy h5py netcdf4 urllib3 glob2 lxml requests
conda install -y --prefix "$OCSMART_ENV" -c conda-forge pyhdf pyproj
conda install -y --prefix "$OCSMART_ENV" -c swordman51 l8angles

export OCSMART_PYTHON="$OCSMART_ENV/bin/python"
export OCSMART_CACHE="$BASE/cache/ocsmart"

"$RUNNER" doctor --backend ocsmart
```

这些依赖和 Python 版本来自官方 v2.2 用户指南。不要把 macOS 下的环境复制到 Linux；
必须在服务器上重新创建。

### 3.3 Earthdata/OB.DAAC 授权

OC-SMART 会下载臭氧、气象和其他 NASA OB.DAAC 辅助数据。先在 Earthdata 账户中
授权 `OB.DAAC Data Access`，然后按官方用户指南配置用户主目录下的 `.netrc` 和
`.urs_cookies`：

```bash
chmod 0600 ~/.netrc
chmod 0600 ~/.urs_cookies
```

认证文件包含敏感信息，不得放进项目目录、Slurm 脚本、命令行参数或 Git。计算节点
不能联网时，应先在允许联网的节点完成一景，让辅助数据进入 `OCSMART_CACHE`。

### 3.4 单景验证

```bash
PRODUCT=$(find "$DATA" -maxdepth 1 -type d -name '*.SAFE' | sort | head -n 1)

"$RUNNER" run "$PRODUCT" \
  --backend ocsmart \
  --output "$BASE/OCSMART_VOMBSJON" \
  --set l2_prod=rrs,chl,tsm
```

官方 v2.2 对 Sentinel-2 MSI 固定采用 60 m，因此 `--resolution` 不生效。输出为：

```text
OCSMART_VOMBSJON/<product-id>/ocsmart/
├── run.json
├── run.log
├── .ocsmart-runtime/
└── <product-id>_L2_OCSMART.h5
```

隐藏运行目录为每景生成官方格式的 `OCSMART_Input.txt`，并通过符号链接只暴露当前
SAFE。它不会修改 `OCSMART_HOME/OCSMART_Input.txt`，也不会扫描和处理相邻产品。

### 3.5 批处理与 Slurm

```bash
"$RUNNER" batch "$DATA" \
  --backend ocsmart \
  --output "$BASE/OCSMART_VOMBSJON" \
  --set l2_prod=rrs,chl,tsm
```

也可提交：

```bash
cd "$APP"
sbatch examples/run_ocsmart_vombsjon.slurm
```

官方建议 Sentinel-2 使用至少 16 GB、较大影像优先 64 GB 内存。若内存有限，可加入
`--set block_size=1024`；分块能降低峰值内存，但会增加运行时间。

## 4. 断点续跑与兼容性

两个后端都沿用现有 `run.json` 语义：成功产品再次执行时自动跳过，失败产品需要确认后
使用 `--force`。`--force` 不删除旧结果，因此不要用它代替正常断点续跑。

现有 ACOLITE、C2RCC 和 POLYMER 结果无需迁移。未来标准化产品会作为新增的
`standardized/` 子目录写入，不会移动或改名这里记录的原生输出。
