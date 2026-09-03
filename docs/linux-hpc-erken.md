# Linux/HPC 上运行 Erken ACOLITE 批处理

Erken 使用 Sentinel-2 L1C 瓦片 `T34VCM`。以下命令沿用
[`linux-hpc.md`](linux-hpc.md) 中的 ACOLITE 环境，只更换输入、ROI 和输出目录。

## 1. 准备路径和 ROI

在服务器上设置：

```bash
export BASE=/projects/eko/fs7/pers/ZC/TWIN_water
export APP="$BASE/s2-inlandwater-ac"
export DATA="$BASE/S2L1C/T34VCM"
export ROI="$BASE/erken.geojson"
export OUT="$BASE/ACOLITE_ERKEN"
export ACENV="$APP/.external/envs/acolite"
```

`DATA` 必须只包含 L1C `.SAFE` 目录或 `.SAFE.zip` 文件。若下载位置不同，修改
`DATA` 即可，不要把 L2A 产品混入该目录。

从 Mac 上传已配置的 Erken 湖区 + 5 km ROI：

```bash
scp \
  /Users/zzcai/Documents/GitHub/s2-l1c-downloader/config/erken.geojson \
  <user>@<linux-host>:/projects/eko/fs7/pers/ZC/TWIN_water/erken.geojson
```

## 2. 检查环境和数据

```bash
export ACOLITE_HOME="$APP/.external/acolite"
export ACOLITE_PYTHON="$ACENV/bin/python"

"$ACENV/bin/s2-water-ac" doctor --backend acolite
find "$DATA" -maxdepth 1 \
  \( -type d -o -type f \) \
  \( -name '*.SAFE' -o -name '*.SAFE.zip' \) | sort | head
```

`doctor` 应显示 `OK acolite`。若环境尚未安装，先执行
[`linux-hpc.md`](linux-hpc.md) 的“在 Linux 上安装 ACOLITE”步骤。

## 3. 先跑一景

```bash
PRODUCT=$(find "$DATA" -maxdepth 1 \
  \( -type d -o -type f \) \
  \( -name '*.SAFE' -o -name '*.SAFE.zip' \) | sort | head -n 1)

test -n "$PRODUCT"

"$ACENV/bin/s2-water-ac" inspect "$PRODUCT"

"$ACENV/bin/s2-water-ac" run "$PRODUCT" \
  --backend acolite \
  --profile inland \
  --resolution 20 \
  --output "$OUT" \
  --set "polygon=$ROI" \
  --set polygon_clip=True \
  --set ancillary_data=False
```

成功后应在 `$OUT/<product-id>/acolite/` 看到 `run.json`、`run.log`、
`*_L2R.nc`、`*_L2W.nc` 和 `*_Rrs_*.tif`。可用下面的命令快速检查：

```bash
find "$OUT" -path '*/acolite/run.json' -exec grep -H '"status": "success"' {} +
find "$OUT" -type f \( -name '*_L2W.nc' -o -name '*_Rrs_*.tif' \) | head
```

## 4. 提交全量 Slurm 任务

```bash
cd "$APP"
sbatch examples/run_acolite_erken.slurm
```

若实际输入目录不同，在提交时覆盖默认值：

```bash
S2_L1C_DIR=/actual/path/to/T34VCM \
  sbatch --export=ALL examples/run_acolite_erken.slurm
```

查看任务和日志：

```bash
squeue -u "$USER"
tail -f "$BASE"/acolite-erken-<job-id>.log
```

已有成功 `run.json` 的景会自动跳过，因此中断后可原样重新提交以继续。断点续跑时
不要添加 `--force`。脚本默认 `ancillary_data=False`；如果服务器已配置 NASA
Earthdata 凭据并需要逐日辅助数据，可以删除该参数。
