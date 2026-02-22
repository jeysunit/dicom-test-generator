"""Core engine data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    age: str | None = Field(None, pattern=r"^\d{3}Y$", description="年齢（例: 044Y）")
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


class SeriesConfig(BaseModel):
    model_config = {"frozen": True}

    series_number: int = Field(..., ge=1, description="シリーズ番号")
    series_description: str | None = Field(None, max_length=64, description="シリーズ説明")
    num_images: int = Field(..., ge=1, le=10000, description="画像枚数")
    protocol_name: str | None = Field(None, description="プロトコル名")
    slice_thickness: float = Field(5.0, gt=0, description="スライス厚（mm）")
    slice_spacing: float = Field(5.0, gt=0, description="スライス間隔（mm）")
    start_z: float = Field(0.0, description="開始Z座標（mm）")


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
    bits_stored: int = Field(12, ge=8, le=16)


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
    uid_method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25"
    uid_custom_root: str | None = Field(None, description="カスタムRoot")
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic
    transfer_syntax: TransferSyntaxConfig
    character_set: CharacterSetConfig
    abnormal: AbnormalConfig = Field(default_factory=AbnormalConfig)
