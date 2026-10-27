"""CR・DX の投影の画像の DICOM の値（docs/spec/06 の 5.5・ADR-0034）.

CR Image IOD（PS3.3 A.2）と Digital X-Ray Image IOD の For Presentation（A.26）の、
CR・DX に固有のモジュールの値を Dataset に書く。Patient・General Study・General
Series の共通の値は DICOMBuilder が書く。通信・ファイル・ログを持たない
（app/core の決まり）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from .exceptions import DICOMBuildError
from .models import SeriesConfig

# SOP Class UID（PS3.4 B.5）
CR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.1"
DX_IMAGE_STORAGE_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.1"
PROJECTION_SOP_CLASSES = {"CR": CR_IMAGE_STORAGE, "DX": DX_IMAGE_STORAGE_FOR_PRESENTATION}

# 画素は 1248 行 × 1024 列・Bits Stored 12・符号なしに固定（Job の画素の大きさには従わない）。
# Imager Pixel Spacing は架空の 0.342 mm（検出器は約 350 × 427 mm）
PROJECTION_ROWS = 1248
PROJECTION_COLUMNS = 1024
PROJECTION_BITS_ALLOCATED = 16
PROJECTION_BITS_STORED = 12
IMAGER_PIXEL_SPACING_MM = 0.342

MONOCHROME1 = "MONOCHROME1"
MONOCHROME2 = "MONOCHROME2"
PHOTOMETRIC_INTERPRETATIONS = (MONOCHROME1, MONOCHROME2)
DEFAULT_PHOTOMETRIC_INTERPRETATION = MONOCHROME2
# DX Image Module（PS3.3 C.8.11.3）：Presentation LUT Shape と Pixel Intensity
# Relationship Sign は Photometric Interpretation に合わせる。LOG で、X 線が強い
# （透過が多い）ほど MONOCHROME2 の画素は小さい（黒い）
PRESENTATION_LUT_SHAPES = {MONOCHROME2: "IDENTITY", MONOCHROME1: "INVERSE"}
PIXEL_INTENSITY_SIGNS = {MONOCHROME2: -1, MONOCHROME1: 1}
PIXEL_INTENSITY_RELATIONSHIP = "LOG"
DX_PRESENTATION_INTENT_TYPE = "FOR PRESENTATION"

# 側面の方向。正面の方向（AP・PA・斜位・側臥位）と Patient Orientation の値が違う
LATERAL_VIEWS = frozenset({"LL", "RL"})
FRONTAL_PATIENT_ORIENTATION = ("L", "F")
LATERAL_PATIENT_ORIENTATION = ("P", "F")


@dataclass(frozen=True)
class Code:
    """Code Sequence Macro の値（PS3.3 Table 8.8-1）."""

    value: str
    scheme: str
    meaning: str

    def item(self) -> Dataset:
        item = Dataset()
        item.CodeValue = self.value
        item.CodingSchemeDesignator = self.scheme
        item.CodeMeaning = self.meaning
        return item


# Anatomic Region Sequence のコード（PS3.16 CID 4031）
ANATOMIC_REGIONS: dict[str, Code] = {
    "CHEST": Code("816094009", "SCT", "Chest"),
    "ABDOMEN": Code("818981001", "SCT", "Abdomen"),
    "LSPINE": Code("122496007", "SCT", "Lumbar spine"),
    "CSPINE": Code("122494005", "SCT", "Cervical spine"),
    "KNEE": Code("72696002", "SCT", "Knee"),
    "HAND": Code("85562004", "SCT", "Hand"),
}
# View Code Sequence のコード（PS3.16 CID 4010）。斜位と側臥位はコードを確かめて
# いないので入れない（View Position だけを書く）
VIEW_CODES: dict[str, Code] = {
    "PA": Code("272479007", "SCT", "postero-anterior"),
    "AP": Code("399348003", "SCT", "antero-posterior"),
    "LL": Code("399173006", "SCT", "left lateral"),
    "RL": Code("399198007", "SCT", "right lateral"),
}

# CR・DX の画像が持たない属性（Frame of Reference・Image Plane と、CT・MR の画像の属性）。
# 装置のプロファイルが足しても外す。DX は Modality LUT を持ってはならない（C.8.11.3）
PROJECTION_ABSENT_KEYWORDS = (
    "FrameOfReferenceUID",
    "PositionReferenceIndicator",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "PixelSpacing",
    "SliceThickness",
    "SliceLocation",
    "SpacingBetweenSlices",
    "PatientPosition",
    "ModalityLUTSequence",
)


def projection_view(series: SeriesConfig, image_index: int) -> str:
    """画像の撮影の方向。`view_positions` が画像の数より少なければ先頭から繰り返す."""
    return series.view_positions[image_index % len(series.view_positions)]


def patient_orientation(view: str) -> list[str]:
    """Patient Orientation (0020,0020)：行の向き・列の向き（PS3.3 C.7.6.1.1.1）.

    正面の画像は患者に向き合って見る向き（行は患者の左、列は足の向き）、側面は
    前から後ろの向きに描くとした値（代表例。docs/spec/06 の 5.5）。
    """
    if view in LATERAL_VIEWS:
        return list(LATERAL_PATIENT_ORIENTATION)
    return list(FRONTAL_PATIENT_ORIENTATION)


def check_photometric_interpretation(value: str) -> str:
    if value not in PHOTOMETRIC_INTERPRETATIONS:
        raise DICOMBuildError(
            f"Photometric Interpretation {value!r} is not allowed for CR/DX "
            f"(allowed: {', '.join(PHOTOMETRIC_INTERPRETATIONS)})",
            tag="PhotometricInterpretation",
        )
    return value


def projection_pixels(pixel_data: np.ndarray, photometric: str) -> np.ndarray:
    """MONOCHROME2 の画素を、符号なしの Bits Stored 12 の uint16 にする.

    uint8（simple_text）は 0〜上限に広げる。int16・uint16 は 0〜上限に収まることを
    確かめる。`MONOCHROME1` は上限から引いた値にする（表示は同じになる）。
    """
    upper = (1 << PROJECTION_BITS_STORED) - 1
    if pixel_data.dtype == np.uint8:
        scaled = np.rint(pixel_data.astype(np.float64) * upper / np.iinfo(np.uint8).max)
        pixels = scaled.astype(np.uint16)
    elif pixel_data.dtype in (np.int16, np.uint16):
        if pixel_data.size and (int(pixel_data.min()) < 0 or int(pixel_data.max()) > upper):
            raise DICOMBuildError(
                f"Pixel values {int(pixel_data.min())}..{int(pixel_data.max())} do not fit "
                f"unsigned Bits Stored {PROJECTION_BITS_STORED} (0..{upper})",
                tag="PixelData",
            )
        pixels = pixel_data.astype(np.uint16)
    else:
        raise DICOMBuildError(
            f"Unsupported pixel data dtype: {pixel_data.dtype}", tag="PixelData"
        )
    if photometric == MONOCHROME1:
        pixels = (upper - pixels).astype(np.uint16)
    return pixels


def set_projection_pixel_data(ds: Dataset, pixels: np.ndarray, photometric: str) -> None:
    """Image Pixel Module と VOI LUT（Window）の値（C.7.6.3・C.11.2）."""
    rows, cols = pixels.shape
    ds.Rows = rows
    ds.Columns = cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = PROJECTION_BITS_ALLOCATED
    ds.BitsStored = PROJECTION_BITS_STORED
    ds.HighBit = PROJECTION_BITS_STORED - 1
    ds.PixelRepresentation = 0
    ds.update(window_attributes())
    ds.PixelData = pixels.tobytes()


def projection_attributes(series: SeriesConfig, image_index: int, photometric: str) -> Dataset:
    """CR Series・CR Image、または DX Series・DX Anatomy Imaged・DX Image・DX Detector・
    DX Positioning・Acquisition Context の値（PS3.3 C.8.1・C.8.11・C.7.6.14）.

    VOI LUT の Window は画素と一緒に `set_projection_pixel_data` が書く。
    """
    modality = series.modality
    if modality not in PROJECTION_SOP_CLASSES:
        raise DICOMBuildError(
            f"A CR/DX image needs a CR or DX series, got {modality}", tag="Modality"
        )
    if series.body_part is None:
        raise DICOMBuildError(f"A {modality} series needs body_part", tag="BodyPartExamined")
    ds = Dataset()
    view = projection_view(series, image_index)
    region = ANATOMIC_REGIONS[series.body_part]
    ds.BodyPartExamined = series.body_part
    ds.ViewPosition = view
    ds.PatientOrientation = patient_orientation(view)
    ds.ImagerPixelSpacing = [str(IMAGER_PIXEL_SPACING_MM), str(IMAGER_PIXEL_SPACING_MM)]
    ds.AnatomicRegionSequence = Sequence([region.item()])
    if modality == "CR":
        # CR Image Module。Image Type は General Image の Type 3
        ds.ImageType = ["ORIGINAL", "PRIMARY"]
        if series.laterality is not None:
            # 対になる部位の左右（General Series の Type 2C。R・L だけ）
            ds.Laterality = series.laterality
        return ds
    # DX Series Module（C.8.11.1）
    ds.PresentationIntentType = DX_PRESENTATION_INTENT_TYPE
    # DX Anatomy Imaged Module（C.8.11.2）。対にならない部位は U
    ds.ImageLaterality = series.laterality or "U"
    # DX Image Module（C.8.11.3）。Image Type の値 3 は長さ 0
    ds.ImageType = ["ORIGINAL", "PRIMARY", ""]
    ds.PixelIntensityRelationship = PIXEL_INTENSITY_RELATIONSHIP
    ds.PixelIntensityRelationshipSign = PIXEL_INTENSITY_SIGNS[photometric]
    ds.RescaleIntercept = "0"
    ds.RescaleSlope = "1"
    ds.RescaleType = "US"
    ds.PresentationLUTShape = PRESENTATION_LUT_SHAPES[photometric]
    ds.LossyImageCompression = "00"
    # Type 1。焼き込みを描かないので、どの方式でも NO
    ds.BurnedInAnnotation = "NO"
    # DX Detector Module（C.8.11.4）。Detector Type は Type 2
    ds.DetectorType = ""
    # DX Positioning Module（C.8.11.5）。Positioner Type は Type 2
    ds.PositionerType = ""
    code = VIEW_CODES.get(view)
    if code is not None:
        ds.ViewCodeSequence = Sequence([code.item()])
    # Acquisition Context Module（C.7.6.14）。Type 2
    ds.AcquisitionContextSequence = Sequence([])
    return ds


def window_attributes() -> Dataset:
    """VOI LUT Module の Window（上限の 1/2 と、4096 段の全体の幅）."""
    upper = (1 << PROJECTION_BITS_STORED) - 1
    ds = Dataset()
    ds.WindowCenter = str((upper + 1) // 2)
    ds.WindowWidth = str(upper + 1)
    return ds


def keep_projection_shape(
    ds: Dataset, series: SeriesConfig, image_index: int, photometric: str
) -> None:
    """装置のプロファイルを重ねた後、CR・DX の画像の形に戻す.

    持たない属性（Frame of Reference・Image Plane など）は外す。必須（Type 1・2・2C）の
    属性は、プロファイルが外したら戻し、Type 1 を空にしたら戻す。プロファイルが `set` で
    書いた値はそのまま。異常のデータはこの後に当てる。
    """
    for keyword in PROJECTION_ABSENT_KEYWORDS:
        if keyword in ds:
            delattr(ds, keyword)
    required = projection_attributes(series, image_index, photometric)
    if series.modality == "DX":
        required.update(window_attributes())
    for element in required:
        keyword = element.keyword
        if not _is_required(series.modality, keyword):
            continue
        if keyword not in ds or (
            keyword not in TYPE2_KEYWORDS and _is_empty(ds[element.tag].value)
        ):
            ds[element.tag] = element


def _is_empty(value: object) -> bool:
    """空の値（None・空の文字・値の無い並び）か。数の 0 は空ではない."""
    if value is None or value == "":
        return True
    if isinstance(value, (str, bytes)):
        return False
    try:
        return len(value) == 0  # type: ignore[arg-type]
    except TypeError:
        return False


# 空を許す必須の属性（Type 2）。ほかの必須の属性は Type 1・1C
TYPE2_KEYWORDS = frozenset(
    {
        "BodyPartExamined",
        "ViewPosition",
        "DetectorType",
        "PositionerType",
        "AcquisitionContextSequence",
    }
)
# 規格が必須にする属性（CR は C.8.1.1・C.7.3.1・C.7.6.1、DX は C.8.11）
CR_REQUIRED_KEYWORDS = frozenset(
    {"BodyPartExamined", "ViewPosition", "PatientOrientation", "Laterality"}
)
DX_REQUIRED_KEYWORDS = frozenset(
    {
        "PatientOrientation",
        "PresentationIntentType",
        "ImageLaterality",
        "AnatomicRegionSequence",
        "ImageType",
        "PixelIntensityRelationship",
        "PixelIntensityRelationshipSign",
        "RescaleIntercept",
        "RescaleSlope",
        "RescaleType",
        "PresentationLUTShape",
        "LossyImageCompression",
        "BurnedInAnnotation",
        "DetectorType",
        "ImagerPixelSpacing",
        "PositionerType",
        "AcquisitionContextSequence",
        "WindowCenter",
        "WindowWidth",
    }
)


# 規格か DTG が値を決める属性。装置のプロファイルの `set` では変えられない（変えると
# C.8.11.3 の決まり（Rescale は恒等、Presentation LUT Shape と Sign は Photometric
# Interpretation に合わせる）や、ルーチンの部位・左右と食い違う）
FIXED_KEYWORDS: dict[str, frozenset[str]] = {
    "CR": frozenset({"Laterality", "BodyPartExamined", "ViewPosition"}),
    "DX": frozenset(
        {
            "PresentationIntentType",
            "ImageLaterality",
            "PixelIntensityRelationship",
            "PixelIntensityRelationshipSign",
            "RescaleIntercept",
            "RescaleSlope",
            "RescaleType",
            "PresentationLUTShape",
            "LossyImageCompression",
            "BurnedInAnnotation",
            "BodyPartExamined",
            "ViewPosition",
        }
    ),
}


def fixed_keywords_set_by(modality: str, keywords: Iterable[str]) -> list[str]:
    """`keywords`（装置のプロファイルの `set`）のうち、CR・DX で変えられない属性."""
    fixed = FIXED_KEYWORDS.get(modality, frozenset())
    return sorted(keyword for keyword in keywords if keyword in fixed)


def _is_required(modality: str | None, keyword: str) -> bool:
    required = CR_REQUIRED_KEYWORDS if modality == "CR" else DX_REQUIRED_KEYWORDS
    return keyword in required
