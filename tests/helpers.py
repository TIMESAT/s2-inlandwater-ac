import zipfile
from pathlib import Path


BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12")
PRODUCT_ID = "S2A_MSIL1C_20210728T103031_N0500_R108_T33UVB_20230127T023918"


def make_safe(root: Path, product_id: str = PRODUCT_ID) -> Path:
    safe = root / (product_id + ".SAFE")
    image_data = safe / "GRANULE" / "L1C_T33UVB_TEST" / "IMG_DATA"
    image_data.mkdir(parents=True)
    (safe / "MTD_MSIL1C.xml").write_text("<root/>", encoding="utf-8")
    (safe / "manifest.safe").write_text("manifest", encoding="utf-8")
    (image_data.parent / "MTD_TL.xml").write_text("<root/>", encoding="utf-8")
    for band in BANDS:
        (image_data / ("T33UVB_TEST_{}.jp2".format(band))).write_bytes(b"")
    return safe


def make_zip(root: Path, product_id: str = PRODUCT_ID) -> Path:
    safe = make_safe(root, product_id)
    archive_path = root / (product_id + ".SAFE.zip")
    with zipfile.ZipFile(str(archive_path), "w") as archive:
        for path in safe.rglob("*"):
            if path.is_file():
                archive.write(str(path), str(path.relative_to(root)))
    return archive_path

