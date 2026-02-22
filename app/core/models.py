"""Core engine data models."""

from __future__ import annotations

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
    size: float | None = Field(None, ge=0, le=3, description="身長（m）")
    patient_comments: str | None = Field(None, max_length=128, description="患者コメント")


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
