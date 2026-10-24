"""撮影のルーチンのシリーズの種類ごとの DICOM の値（docs/spec/06・ADR-0025）.

通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

from .models import SeriesConfig, SpatialCoordinates

# Image Type (0008,0008)。CT Image の Value 3 は AXIAL か LOCALIZER（PS3.3 C.8.2.1.1.1）。
# 同じ節の注のとおり、冠状断・矢状断も断面の画像なので AXIAL にする。線量の画面は
# Secondary Capture（Value 3 は付けない）
IMAGE_TYPES: dict[str, tuple[str, ...]] = {
    "axial": ("ORIGINAL", "PRIMARY", "AXIAL"),
    "localizer": ("ORIGINAL", "PRIMARY", "LOCALIZER"),
    "coronal": ("DERIVED", "SECONDARY", "AXIAL"),
    "sagittal": ("DERIVED", "SECONDARY", "AXIAL"),
    "dose_report": ("DERIVED", "SECONDARY"),
}

# Image Orientation (Patient) (0020,0037)。行の向きと列の向き（PS3.3 C.7.6.2.1.1）
AXIAL_ORIENTATION = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
CORONAL_ORIENTATION = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]
SAGITTAL_ORIENTATION = [0.0, 1.0, 0.0, 0.0, 0.0, -1.0]
VIEW_ORIENTATIONS = {"frontal": CORONAL_ORIENTATION, "lateral": SAGITTAL_ORIENTATION}

# 造影のシリーズの Contrast/Bolus Agent (0018,0010)（PS3.3 C.7.6.4。架空の検査の値）
CONTRAST_AGENT = "IOPAMIDOL"


# 線量の画面に描く架空の値（実の線量ではない。ADR-0025）
DOSE_REPORT_CTDI_VOL_MGY = 10.0
DOSE_REPORT_LOCALIZER_CTDI_VOL_MGY = 0.1
DOSE_REPORT_ROWS_PER_PAGE = 18


def dose_report_lines(series_list: list[SeriesConfig], page: int = 0) -> list[str]:
    """線量の画面の文字の行。撮影したシリーズ（位置決め・軸位）ごとに架空の CTDIvol と
    DLP を並べる。冠状断・矢状断は作り直した画像なので線量の行に入れない.

    `page` は線量の画面の何枚目か（0 始まり）。1 枚に収まらない行は次の画面に回す。
    """
    rows = [
        series
        for series in series_list
        if series.kind in ("localizer", "axial")
    ]
    start = page * DOSE_REPORT_ROWS_PER_PAGE
    lines = [
        "Dose Report",
        f"Page {page + 1}",
        "",
        "Series  Type       CTDIvol(mGy)  DLP(mGy*cm)",
    ]
    for series in rows[start : start + DOSE_REPORT_ROWS_PER_PAGE]:
        ctdi, dlp = _dose(series)
        lines.append(f"{series.series_number:<7} {series.kind:<10} {ctdi:>12.2f}  {dlp:>11.2f}")
    total = sum(_dose(series)[1] for series in rows)
    lines.extend(["", f"Total DLP {total:.2f} mGy*cm"])
    return lines


def _dose(series: SeriesConfig) -> tuple[float, float]:
    """架空の CTDIvol と、撮影の長さ（枚数×間隔）を掛けた DLP."""
    ctdi = DOSE_REPORT_LOCALIZER_CTDI_VOL_MGY if series.kind == "localizer" else (
        DOSE_REPORT_CTDI_VOL_MGY
    )
    length_cm = series.num_images * series.slice_spacing / 10
    return ctdi, ctdi * length_cm


def image_type(series: SeriesConfig) -> list[str]:
    return list(IMAGE_TYPES[series.kind])


def localizer_view(series: SeriesConfig, image_index: int) -> str:
    """位置決めの画像の方向。`views` が画像の数より少なければ先頭から繰り返す."""
    return series.views[image_index % len(series.views)]


def series_spatial(series: SeriesConfig, image_index: int) -> SpatialCoordinates:
    """シリーズの種類ごとの画像の位置と向き.

    軸位は z、冠状断は前後（y）、矢状断は左右（x）の向きに、スライス間隔ずつ進める。
    位置決めは投影の画像なので、どの画像も原点に置き、向きだけを方向で変える。
    """
    if image_index < 0:
        raise ValueError(f"image_index must be >= 0, got {image_index}")
    offset = series.start_z + image_index * series.slice_spacing
    if series.kind == "localizer":
        position, location = [0.0, 0.0, 0.0], 0.0
        orientation = VIEW_ORIENTATIONS[localizer_view(series, image_index)]
    elif series.kind == "coronal":
        position, location, orientation = [0.0, offset, 0.0], offset, CORONAL_ORIENTATION
    elif series.kind == "sagittal":
        position, location, orientation = [offset, 0.0, 0.0], offset, SAGITTAL_ORIENTATION
    else:
        position, location, orientation = [0.0, 0.0, offset], offset, AXIAL_ORIENTATION
    return SpatialCoordinates(
        instance_number=image_index + 1,
        image_position_patient=position,
        slice_location=location,
        image_orientation_patient=list(orientation),
    )
