# Linux/HPC 上运行 Vombsjön ACOLITE 批处理

本文使用以下目录：

```bash
export BASE=/projects/eko/fs7/pers/ZC/TWIN_water
export APP="$BASE/s2-inlandwater-ac"
export DATA="$BASE/S2L1C/T33UVB"
export ROI="$BASE/vombsjon.geojson"
export OUT="$BASE/ACOLITE_VOMBSJON"
export ACENV="$APP/.external/envs/acolite"
```

## 1. 同步代码和 ROI

如果服务器上还没有本仓库：

```bash
cd "$BASE"
git clone https://github.com/TIMESAT/s2-inlandwater-ac.git
mkdir -p "$APP/.external/envs"
```

`vombsjon.geojson` 包含 Vombsjön 搜索范围和湖区外扩约 5 km 的处理范围。可在
Mac 终端上传它（替换服务器登录名和地址）：

```bash
scp \
  /Users/zzcai/Documents/GitHub/s2-l1c-downloader/config/vombsjon.geojson \
  <user>@<linux-host>:/projects/eko/fs7/pers/ZC/TWIN_water/vombsjon.geojson
```

处理 ROI 完全包含搜索范围，因此 ACOLITE 读取这个 FeatureCollection 后得到的裁剪
外包范围和多边形并集就是 5 km 处理 ROI。

## 2. 在 Linux 上安装 ACOLITE

macOS 下已有的 `.external/envs/acolite` 不能在 Linux 上运行。先加载服务器提供的
conda、mamba 或 micromamba 模块，然后在 Linux 上重新创建环境。ACOLITE 官方推荐
从源码仓库的 `environment.yml` 创建环境：

```bash
mkdir -p "$APP/.external/envs"
cd "$APP/.external"

git clone --depth 1 https://github.com/acolite/acolite.git acolite

conda env create \
  --prefix "$ACENV" \
  --file "$APP/.external/acolite/environment.yml"

"$ACENV/bin/python" -m pip install -e "$APP"
```

若使用 micromamba，可将环境创建命令替换为：

```bash
micromamba create -y \
  --prefix "$ACENV" \
  --file "$APP/.external/acolite/environment.yml"
```

设置处理器路径并检查安装：

```bash
export ACOLITE_HOME="$APP/.external/acolite"
export ACOLITE_PYTHON="$ACENV/bin/python"

"$ACENV/bin/s2-water-ac" doctor --backend acolite
```

检查结果应显示 `OK acolite`。ACOLITE 首次实际处理时会自动下载 LUT；如果计算节点
不能访问互联网，应先在可联网节点处理一景，让 LUT 缓存在 ACOLITE 数据目录中。

## 3. 单景验证

先选择一景检查 Linux 环境、ROI 和输出权限：

```bash
PRODUCT=$(find "$DATA" -maxdepth 1 -type d -name '*.SAFE' | sort | head -n 1)

"$ACENV/bin/s2-water-ac" run "$PRODUCT" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$OUT" \
  --set "polygon=$ROI" \
  --set polygon_clip=True \
  --set ancillary_data=False
```

每景结果保存为：

```text
ACOLITE_VOMBSJON/<product-id>/acolite/
├── run.json
├── run.log
├── acolite-settings.txt
├── *_L2R.nc
├── *_L2W.nc
└── *_Rrs_*.tif
```

## 4. 全量串行批处理

确认单景成功后运行：

```bash
"$ACENV/bin/s2-water-ac" batch "$DATA" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$OUT" \
  --set "polygon=$ROI" \
  --set polygon_clip=True \
  --set ancillary_data=False
```

批处理默认按景串行执行，单景失败时记录错误并继续。已有成功 `run.json` 的产品会自动
跳过，所以任务被中断后可重新运行同一命令继续。不要为断点续跑添加 `--force`；该参数
可能使新文件和旧文件混在同一结果目录。

`ancillary_data=False` 与本项目首次验证使用的配置一致，采用 ACOLITE 默认臭氧、水汽和
气压。若已配置 NASA Earthdata 凭据并希望使用逐日辅助数据，可以移除此参数。

## 5. Slurm 提交

仓库提供了默认路径已配置好的脚本：

```bash
cd "$APP"
sbatch examples/run_acolite_vombsjon.slurm
```

查看状态和日志：

```bash
squeue -u "$USER"
tail -f "$BASE"/acolite-<job-id>.log
```

不同集群的 partition、account、内存和最长运行时间不同。如集群要求 `--partition` 或
`--account`，在脚本头部补充对应的 `#SBATCH` 参数。

脚本中的默认路径可通过环境变量覆盖；部分 Slurm 配置需要使用 `--export=ALL` 才会传递
提交环境，例如：

```bash
S2_AC_OUTPUT="$BASE/ACOLITE_TEST" \
  sbatch --export=ALL examples/run_acolite_vombsjon.slurm
```

## 6. 结果和空间估算

Vombsjön 5 km ROI 的一次 20 m 测试耗时约 11.5 秒，产生约 209 MB 输出；实际耗时和
大小会随云量、文件系统速度、ACOLITE 版本和输出参数变化。提交全量任务前，可用影像数
乘以单景实测大小估算空间，并为 NetCDF/GeoTIFF 临时写入预留余量。

ACOLITE 官方安装说明：<https://github.com/acolite/acolite/blob/main/README.md>
