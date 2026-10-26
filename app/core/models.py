"""Core engine data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError


class PatientName(BaseModel):
    model_config = {"frozen": True}

    alphabetic: str = Field(..., description="ローマ字表記（例: YAMADA^TARO）")
    ideographic: str | None = Field(None, description="漢字表記（例: 山田^太郎）")
    phonetic: str | None = Field(None, description="カナ表記（例: ヤマダ^タロウ）")

    def to_dicom_pn(self, use_ideographic: bool, use_phonetic: bool) -> str:
        """DICOM PN形式に変換"""
        parts = [self.alphabetic]
        if use_ideographic and self.ideographic:
            parts.append(self.ideographic)
        else:
            parts.append("")

        if use_phonetic and self.phonetic:
            parts.append(self.phonetic)
        else:
            parts.append("")

        # 末尾の空コンポーネント削除
        while parts and parts[-1] == "":
            parts.pop()

        return "=".join(parts) if len(parts) > 1 else parts[0]


class Patient(BaseModel):
    model_config = {"frozen": True}

    patient_id: str = Field(..., max_length=16, description="患者ID")
    patient_name: PatientName
    birth_date: str = Field(..., pattern=r"^\d{8}$", description="生年月日（YYYYMMDD）")
    sex: str = Field(..., pattern=r"^(M|F|O)$", description="性別")
    age: str | None = Field(None, pattern=r"^\d{3}Y$",
        description="年齢入力（互換用。DICOM出力は birth_date/study_date から日本法基準で算出）")
    weight: float | None = Field(None, ge=0, le=500, description="体重（kg）")
    size: float | None = Field(None, ge=0, le=300, description="身長（cm）")
    patient_comments: str | None = Field(None, max_length=128, description="患者コメント")

    @property
    def size_in_meters(self) -> float | None:
        """DICOM Patient's Size (0010,1020) 用にメートル単位で返す."""
        if self.size is None:
            return None
        return self.size / 100.0


class StudyConfig(BaseModel):
    model_config = {"frozen": True}

    accession_number: str = Field(..., max_length=16, description="Accession Number")
    study_date: str = Field(..., pattern=r"^\d{8}$", description="検査日")
    study_time: str = Field(..., pattern=r"^\d{6}$", description="検査時刻")
    study_description: str | None = Field(None, max_length=64, description="検査説明")
    referring_physician_name: str | None = Field(None, description="紹介医名")
    num_series: int = Field(..., ge=1, le=100, description="シリーズ数")


CTSeriesKind = Literal["axial", "localizer", "coronal", "sagittal", "dose_report"]
# MR のシリーズの種類。位置決めは CT と同じ "localizer"（ADR-0030）
MRSeriesKind = Literal["localizer", "acquisition", "derived"]
SeriesKind = Literal[
    "axial", "localizer", "coronal", "sagittal", "dose_report", "acquisition", "derived"
]
SeriesModality = Literal["CT", "MR"]
MRPlane = Literal["axial", "sagittal", "coronal", "three_plane"]
# Scanning Sequence (0018,0020) の値（PS3.3 C.8.3.1。RM は使わない）
MRSequence = Literal["SE", "IR", "GR", "EP"]
# MR Acquisition Type (0018,0023) の値（PS3.3 C.8.3.1）
MRAcquisitionType = Literal["2D", "3D"]
LocalizerView = Literal["frontal", "lateral"]


class SeriesConfig(BaseModel):
    model_config = {"frozen": True}

    series_number: int = Field(..., ge=1, description="シリーズ番号")
    series_description: str | None = Field(None, max_length=64, description="シリーズ説明")
    num_images: int = Field(..., ge=1, le=10000, description="画像枚数")
    protocol_name: str | None = Field(None, description="プロトコル名")
    slice_thickness: float = Field(5.0, gt=0, description="スライス厚（mm）")
    slice_spacing: float = Field(5.0, gt=0, description="スライス間隔（mm）")
    start_z: float = Field(0.0, description="開始Z座標（mm）")
    # 撮影のルーチンのシリーズの種類（docs/spec/03・ADR-0025）。既定の axial は今までの画像
    kind: SeriesKind = Field("axial", description="シリーズの種類")
    # 位置決めの画像ごとの方向。足りなければ先頭から繰り返す
    views: list[LocalizerView] = Field(default_factory=lambda: ["frontal"], min_length=1)
    contrast: bool = Field(False, description="造影のシリーズ（Contrast/Bolus Agent を入れる）")
    # このシリーズのモダリティ (0008,0060)。None はテンプレートのモダリティ（ADR-0030）
    modality: SeriesModality | None = Field(None, description="シリーズのモダリティ")
    # MR のシリーズの断面と撮像（MR 以外では使わない）
    plane: MRPlane = Field("axial", description="MR の断面")
    sequence: MRSequence = Field("SE", description="MR の Scanning Sequence")
    acquisition_type: MRAcquisitionType = Field("2D", description="MR Acquisition Type")

    @model_validator(mode="after")
    def _kind_matches_modality(self) -> SeriesConfig:
        mr_kinds = ("acquisition", "derived")
        if self.modality == "MR" and self.kind in ("axial", "coronal", "sagittal", "dose_report"):
            raise ValueError(f"kind {self.kind!r} is not an MR series kind")
        if self.modality == "CT" and self.kind in mr_kinds:
            raise ValueError(f"kind {self.kind!r} needs modality MR")
        if self.modality is None and self.kind in mr_kinds:
            raise ValueError(f"kind {self.kind!r} needs modality MR")
        if self.modality == "MR" and self.contrast:
            # MR の造影（Contrast/Bolus Module）はまだ作らない（ADR-0030）
            raise ValueError("contrast is not supported for MR series")
        return self


class InstanceConfig(BaseModel):
    model_config = {"frozen": True}

    instance_number: int = Field(..., ge=1, description="インスタンス番号")
    acquisition_number: int = Field(1, ge=1, description="Acquisition Number")


class UIDContext(BaseModel):
    model_config = {"frozen": True}

    study_instance_uid: str
    frame_of_reference_uid: str
    implementation_class_uid: str
    instance_creator_uid: str


class SpatialCoordinates(BaseModel):
    model_config = {"frozen": True}

    instance_number: int = Field(..., ge=1)
    image_position_patient: list[float] = Field(..., min_length=3, max_length=3)
    slice_location: float
    image_orientation_patient: list[float] = Field(
        default=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        min_length=6,
        max_length=6,
    )
    pixel_spacing: list[float] = Field(
        default=[0.5, 0.5],
        min_length=2,
        max_length=2,
    )


class PixelSpecSimple(BaseModel):
    """Simple Textモードピクセル設定."""

    model_config = {"frozen": True}

    mode: Literal["simple_text"] = "simple_text"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    background_color: int = Field(0, ge=0, le=255)
    text_color: int = Field(255, ge=0, le=255)
    font_size: int = Field(24, ge=8, le=72)


class PixelSpecCTRealistic(BaseModel):
    """CT Realisticモードピクセル設定."""

    model_config = {"frozen": True}

    mode: Literal["ct_realistic"] = "ct_realistic"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    pattern: Literal["gradient", "circle", "noise"] = "gradient"
    # CT Image の Bits Stored は 12〜16（PS3.3 C.8.2.1.1.5）
    bits_stored: int = Field(12, ge=12, le=16)


PixelSpec = PixelSpecSimple | PixelSpecCTRealistic


class TransferSyntaxConfig(BaseModel):
    """Transfer Syntax設定."""

    model_config = {"frozen": True}

    uid: str = Field("1.2.840.10008.1.2", description="Transfer Syntax UID")
    name: str = Field("Implicit VR Little Endian", description="名称")
    is_implicit_vr: bool = Field(True, description="Implicit VR か")
    is_little_endian: bool = Field(True, description="Little Endian か")


class CharacterSetConfig(BaseModel):
    """文字セット設定."""

    model_config = {"frozen": True}

    specific_character_set: str = Field(
        r"ISO 2022 IR 6\ISO 2022 IR 87", description="Specific Character Set"
    )
    use_ideographic: bool = Field(True, description="漢字を使用するか")
    use_phonetic: bool = Field(True, description="カナを使用するか")


class AbnormalConfig(BaseModel):
    """異常生成設定."""

    model_config = {"frozen": True}

    level: Literal["none", "mild", "moderate", "severe"] = "none"
    allow_invalid_sop_uid: bool = Field(False, description="SOP UID 0始まり不正を許可")
    invalid_sop_uid_probability: float = Field(
        0.1, ge=0.0, le=1.0, description="不正UID生成確率"
    )


class GenerationConfig(BaseModel):
    """DICOM生成全体設定（Jobファイルから読み込む）."""

    model_config = {"frozen": True}

    job_name: str = Field(..., description="ジョブ名")
    output_dir: str = Field(..., description="出力ディレクトリ")
    patient: Patient
    study: StudyConfig
    series_list: list[SeriesConfig] = Field(..., min_length=1, max_length=100)
    modality_template: str = Field(..., description="モダリティテンプレート名")
    hospital_template: str | None = Field(None, description="病院テンプレート名")
    device_profile: str | None = Field(None, description="装置のプロファイル名（docs/spec/13）")
    uid_method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25"
    uid_custom_root: str | None = Field(None, description="カスタムRoot")
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic
    transfer_syntax: TransferSyntaxConfig
    character_set: CharacterSetConfig
    abnormal: AbnormalConfig = Field(default_factory=AbnormalConfig)

    @model_validator(mode="after")
    def validate_date_consistency(self) -> GenerationConfig:
        try:
            birth_date = datetime.strptime(self.patient.birth_date, "%Y%m%d").date()
            study_date = datetime.strptime(self.study.study_date, "%Y%m%d").date()
        except ValueError as exc:
            raise PydanticCustomError(
                "invalid_calendar_date",
                "birth_date/study_date must be valid calendar dates: {reason}",
                {"reason": str(exc)},
            ) from exc

        if study_date < birth_date:
            raise PydanticCustomError(
                "invalid_date_order",
                "study.study_date must be on or after patient.birth_date",
                {},
            )
        return self


# --- モダリティのダミー（docs/spec/12_modality_emulator.md・docs/spec/03_data_models.md）---

PATIENT_ID_MAX_LENGTH = 64
DicomJsonSequences = dict[str, list[dict]]


class WorklistItem(BaseModel):
    """ワークリストの1件（C-FIND MWL の応答）を読んだ値."""

    model_config = {"frozen": True}

    key: str = Field(..., description="予約の鍵（SHA-1 の先頭 10 桁）")
    patient_name: str = ""
    patient_id: str = ""
    issuer_of_patient_id: str = ""
    birth_date: str = ""
    sex: str = ""
    weight: str = ""
    size: str = ""
    study_instance_uid: str = ""
    accession_number: str = ""
    referring_physician_name: str = ""
    # 依頼医 (0032,1032)。画面に出すだけで、画像には写さない（docs/spec/12 の 5.2）
    requesting_physician: str = ""
    requested_procedure_id: str = ""
    requested_procedure_description: str = ""
    reason_for_requested_procedure: str = ""
    scheduled_procedure_step_id: str = ""
    scheduled_procedure_step_description: str = ""
    scheduled_start_date: str = ""
    scheduled_start_time: str = ""
    modality: str = ""
    scheduled_station_ae_title: str = ""
    institution_name: str = ""
    # 部位 (0018,0015)。MWL の標準の返却の値ではなく、RIS が返したときだけ入る。ルーチンを
    # 当てるのに使う（docs/spec/12 の 5.2・ADR-0025）
    body_part_examined: str = ""
    specific_character_set: list[str] = Field(default_factory=list)
    sequences: DicomJsonSequences = Field(default_factory=dict)
    unreadable_attributes: list[str] = Field(default_factory=list)


class ScheduledPatient(BaseModel):
    """予約から写す患者の値。生年月日・性別の空を許す（Patient とは別）."""

    model_config = {"frozen": True}

    patient_id: str = Field(..., min_length=1, max_length=PATIENT_ID_MAX_LENGTH)
    patient_name: str = Field(..., description="PN の文字列（=・^ 区切り）")
    issuer_of_patient_id: str = ""
    birth_date: str = Field("", pattern=r"^(\d{8})?$")
    sex: str = Field("", pattern=r"^(M|F|O)?$")
    weight: str = ""
    size: str = ""


class ScheduledContext(BaseModel):
    """画像に写す予約の値（予約あり・予約なしの両方）."""

    model_config = {"frozen": True}

    scheduled: bool
    patient: ScheduledPatient
    study_instance_uid: str | None = None
    accession_number: str = ""
    referring_physician_name: str = ""
    study_id: str = ""
    study_description: str = ""
    performed_procedure_step_id: str
    # MPPS を使うときの MPPS の SOP Instance UID。画像の Referenced Performed
    # Procedure Step Sequence に写す（IHE RAD TF-2x A.1.3・A.2.2）
    performed_procedure_step_sop_instance_uid: str = ""
    institution_name: str = ""
    request_attributes: dict | None = None
    sequences: DicomJsonSequences = Field(default_factory=dict)
    specific_character_set: list[str] = Field(default_factory=list)
    source_ae_title: str = ""
    # 撮影した装置の Station Name (0008,1010)。空ならテンプレート・プロファイル・病院の値
    station_name: str = ""
    # PPS の開始日時（YYYYMMDD・HHMMSS）。空なら Study Date・Time と同じ。追加撮影では
    # Study の日時は最初の撮影の値で、PPS はその撮影の日時になる（IHE RAD TF-2x Table A.1-3）
    performed_procedure_step_start_date: str = ""
    performed_procedure_step_start_time: str = ""
    # True なら study_description が空でも写す（テンプレートの説明を消す）。追加撮影で、
    # 最初の撮影の説明（空を含む）に揃える（IHE RAD TF-2x の IHE-A.3.3）
    study_description_fixed: bool = False
