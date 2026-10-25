"""撮影のルーチンのシリーズの種類ごとの DICOM の値（docs/spec/06・ADR-0025）.

通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

from dataclasses import dataclass

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
    # PET Image：再構成した画像は ORIGINAL\PRIMARY（PS3.3 C.8.9.4.1.1 の Note）
    "pet_ac": ("ORIGINAL", "PRIMARY"),
    "pet_nac": ("ORIGINAL", "PRIMARY"),
}
# PET の画像の行列（架空）と視野（mm）。画素間隔は 視野 ÷ 行列
PET_MATRIX_SIZE = 128
PET_FIELD_OF_VIEW_MM = 700.0
# MR Image の Image Type は Type 1 で値の定めは無い（PS3.3 C.8.3.1.1.1）。装置が出す形に
# 合わせ、撮像した画像は M（強度画像）・ND（再構成の補正なし）、計算で作った画像は
# DERIVED\SECONDARY にする
MR_IMAGE_TYPES: dict[str, tuple[str, ...]] = {
    "localizer": ("ORIGINAL", "PRIMARY", "M", "ND"),
    "acquisition": ("ORIGINAL", "PRIMARY", "M", "ND"),
    "derived": ("DERIVED", "SECONDARY"),
}
# MR の画素間隔は、視野（架空の 240 mm）を画素数で割った値にする
MR_FIELD_OF_VIEW_MM = 240.0
# 三方向の位置決めの断面の順（画像を三等分して順に割り当てる）
THREE_PLANE_ORDER = ("axial", "coronal", "sagittal")


@dataclass(frozen=True)
class MRSequenceParameters:
    """Scanning Sequence ごとの MR Image Module の値（PS3.3 C.8.3.1。架空の撮像条件）."""

    sequence_variant: tuple[str, ...]
    repetition_time_ms: float
    echo_time_ms: float
    echo_train_length: int
    inversion_time_ms: float | None = None


# Inversion Time は Scanning Sequence に IR を含むとき必須（Type 2C）。Repetition Time は
# EP 以外か Sequence Variant が SK のとき必須（Type 2C）で、EP にも入れておく
MR_SEQUENCE_PARAMETERS: dict[str, MRSequenceParameters] = {
    "SE": MRSequenceParameters(("SK",), 3000.0, 90.0, 15),
    "IR": MRSequenceParameters(("SK",), 9000.0, 100.0, 15, inversion_time_ms=2500.0),
    "GR": MRSequenceParameters(("SP",), 600.0, 15.0, 1),
    "EP": MRSequenceParameters(("NONE",), 5000.0, 80.0, 1),
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
    rows = dose_events(series_list)
    start = page * DOSE_REPORT_ROWS_PER_PAGE
    lines = [
        "Dose Report",
        f"Page {page + 1}",
        "",
        "Series  Type       CTDIvol(mGy)  DLP(mGy*cm)",
    ]
    for series in rows[start : start + DOSE_REPORT_ROWS_PER_PAGE]:
        ctdi, dlp = series_dose(series)
        lines.append(f"{series.series_number:<7} {series.kind:<10} {ctdi:>12.2f}  {dlp:>11.2f}")
    total = sum(series_dose(series)[1] for series in rows)
    lines.extend(["", f"Total DLP {total:.2f} mGy*cm"])
    return lines


def dose_events(series_list: list[SeriesConfig]) -> list[SeriesConfig]:
    """線量の報告に載せる撮影（位置決め・軸位のシリーズ）。線量の画面と同じ並び."""
    return [series for series in series_list if series.kind in ("localizer", "axial")]


def series_dose(series: SeriesConfig) -> tuple[float, float]:
    """架空の CTDIvol と、撮影の長さ（枚数×間隔）を掛けた DLP."""
    ctdi = DOSE_REPORT_LOCALIZER_CTDI_VOL_MGY if series.kind == "localizer" else (
        DOSE_REPORT_CTDI_VOL_MGY
    )
    length_cm = series.num_images * series.slice_spacing / 10
    return ctdi, ctdi * length_cm


def image_type(series: SeriesConfig) -> list[str]:
    if series.modality == "MR":
        return list(MR_IMAGE_TYPES[series.kind])
    return list(IMAGE_TYPES[series.kind])


def mr_plane(series: SeriesConfig, image_index: int) -> tuple[str, int]:
    """MR の画像の断面と、その断面の中の画像の位置（0 始まり）.

    三方向（three_plane）は画像を断面の数で等分し、順に axial・coronal・sagittal に
    割り当てる。割り切れない余りは最後の断面に入れる。
    """
    if series.plane != "three_plane":
        return series.plane, image_index
    per_plane = max(1, series.num_images // len(THREE_PLANE_ORDER))
    plane_index = min(image_index // per_plane, len(THREE_PLANE_ORDER) - 1)
    return THREE_PLANE_ORDER[plane_index], image_index - plane_index * per_plane


def _mr_spatial(series: SeriesConfig, image_index: int) -> SpatialCoordinates:
    """MR の画像の位置と向き。断面ごとに、CT の断面の画像と同じ軸へ間隔ずつ進める."""
    plane, position_index = mr_plane(series, image_index)
    offset = series.start_z + position_index * series.slice_spacing
    if plane == "coronal":
        position, orientation = [0.0, offset, 0.0], CORONAL_ORIENTATION
    elif plane == "sagittal":
        position, orientation = [offset, 0.0, 0.0], SAGITTAL_ORIENTATION
    else:
        position, orientation = [0.0, 0.0, offset], AXIAL_ORIENTATION
    return SpatialCoordinates(
        instance_number=image_index + 1,
        image_position_patient=position,
        slice_location=offset,
        image_orientation_patient=list(orientation),
    )


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
    if series.modality == "MR":
        return _mr_spatial(series, image_index)
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
