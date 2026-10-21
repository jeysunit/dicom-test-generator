# 03. データモデル定義

## 概要

このドキュメントでは、アプリケーション全体で使用するデータモデル（Pythonクラス）を定義する。

**実装方針**:

- **Pydantic v2** を使用（型検証・シリアライズ）
- `app/core/models.py` の各モデルは Immutable（`model_config = {"frozen": True}`）
- 明確なデフォルト値

この文書のコードは、型と制約を示すために書き写したものである。正本は
`app/core/models.py` で、食い違ったらコードが正しい。`GenerationConfig` を
含むモデルの全体は同じファイルにある。

---

## Patient（患者情報）

```python
from pydantic import BaseModel, Field

class PatientName(BaseModel):
    """患者名（PN型）"""
    alphabetic: str = Field(..., description="ローマ字表記（例: YAMADA^TARO）")
    ideographic: str | None = Field(None, description="漢字表記（例: 山田^太郎）")
    phonetic: str | None = Field(None, description="カナ表記（例: ヤマダ^タロウ）")
    
    def to_dicom_pn(self, use_ideographic: bool, use_phonetic: bool) -> str:
        """DICOM PN形式に変換
        
        Returns:
            str: "YAMADA^TARO" or "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"
        """
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
    """患者情報"""
    patient_id: str = Field(..., max_length=16, description="患者ID")
    patient_name: PatientName
    birth_date: str = Field(..., pattern=r"^\d{8}$", description="生年月日（YYYYMMDD）")
    sex: str = Field(..., pattern=r"^(M|F|O)$", description="性別")
    age: str | None = Field(
        None,
        pattern=r"^\d{3}Y$",
        description="年齢入力（互換用。DICOM出力は birth_date/study_date から日本法基準で算出）",
    )
    weight: float | None = Field(None, ge=0, le=500, description="体重（kg）")
    size: float | None = Field(None, ge=0, le=300, description="身長（cm）")
    patient_comments: str | None = Field(None, max_length=128, description="患者コメント")

    @property
    def size_in_meters(self) -> float | None:
        """DICOM Patient's Size (0010,1020) 用にメートル単位で返す."""
        ...
```

`size` は cm で持ち、DICOM に書くときに m へ換算する
（[ADR-0007](../adr/0007-patient-size-in-centimeters.md)）。

---

## Study（スタディ情報）

```python
class StudyConfig(BaseModel):
    """スタディ設定"""
    accession_number: str = Field(..., max_length=16, description="Accession Number")
    study_date: str = Field(..., pattern=r"^\d{8}$", description="検査日（YYYYMMDD）")
    study_time: str = Field(..., pattern=r"^\d{6}$", description="検査時刻（HHMMSS）")
    study_description: str | None = Field(None, max_length=64, description="検査説明")
    referring_physician_name: str | None = Field(None, description="紹介医名")
    num_series: int = Field(..., ge=1, le=100, description="シリーズ数")
```

---

## Series（シリーズ情報）

```python
class SeriesConfig(BaseModel):
    """シリーズ設定"""
    series_number: int = Field(..., ge=1, description="シリーズ番号")
    series_description: str | None = Field(None, max_length=64, description="シリーズ説明")
    num_images: int = Field(..., ge=1, le=10000, description="画像枚数")
    protocol_name: str | None = Field(None, description="プロトコル名")
    
    # 空間座標設定
    slice_thickness: float = Field(5.0, gt=0, description="スライス厚（mm）")
    slice_spacing: float = Field(5.0, gt=0, description="スライス間隔（mm）")
    start_z: float = Field(0.0, description="開始Z座標（mm）")
```

---

## Instance（画像インスタンス情報）

```python
class InstanceConfig(BaseModel):
    """画像インスタンス設定"""
    instance_number: int = Field(..., ge=1, description="インスタンス番号")
    acquisition_number: int = Field(1, ge=1, description="Acquisition Number")
```

---

## UID Context

```python
class UIDContext(BaseModel):
    """UID情報を一元管理"""
    study_instance_uid: str
    frame_of_reference_uid: str
    implementation_class_uid: str
    instance_creator_uid: str
    
    # Series/Instance UIDは動的生成のため含めない
```

---

## Pixel Spec

```python
class PixelSpecSimple(BaseModel):
    """Simple Textモードピクセル設定"""
    mode: Literal["simple_text"] = "simple_text"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    background_color: int = Field(0, ge=0, le=255)
    text_color: int = Field(255, ge=0, le=255)
    font_size: int = Field(24, ge=8, le=72)

class PixelSpecCTRealistic(BaseModel):
    """CT Realisticモードピクセル設定"""
    mode: Literal["ct_realistic"] = "ct_realistic"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    pattern: Literal["gradient", "circle", "noise"] = "gradient"
    bits_stored: int = Field(12, ge=12, le=16)  # CT は 12〜16（PS3.3 C.8.2.1.1.5）

PixelSpec = PixelSpecSimple | PixelSpecCTRealistic
```

---

## Transfer Syntax

```python
class TransferSyntaxConfig(BaseModel):
    """Transfer Syntax設定"""
    uid: str = Field("1.2.840.10008.1.2", description="Transfer Syntax UID")
    name: str = Field("Implicit VR Little Endian", description="名称")
    is_implicit_vr: bool = Field(True, description="Implicit VR か")
    is_little_endian: bool = Field(True, description="Little Endian か")
```

---

## Character Set

```python
class CharacterSetConfig(BaseModel):
    """文字セット設定"""
    specific_character_set: str = Field("ISO 2022 IR 6\\ISO 2022 IR 87", description="Specific Character Set")
    use_ideographic: bool = Field(True, description="漢字を使用するか")
    use_phonetic: bool = Field(True, description="カナを使用するか")
```

---

## Abnormal Config

```python
class AbnormalConfig(BaseModel):
    """異常生成設定"""
    level: Literal["none", "mild", "moderate", "severe"] = "none"
    allow_invalid_sop_uid: bool = Field(False, description="SOP UID 0始まり不正を許可")
    invalid_sop_uid_probability: float = Field(0.1, ge=0.0, le=1.0, description="不正UID生成確率")
```

---

## Generation Config（総合設定）

```python
class GenerationConfig(BaseModel):
    """DICOM生成全体設定（Jobファイルから読み込む）"""
    
    # 基本情報
    job_name: str = Field(..., description="ジョブ名")
    output_dir: str = Field(..., description="出力ディレクトリ")
    
    # 患者情報
    patient: Patient
    
    # スタディ情報
    study: StudyConfig
    
    # シリーズ情報（可変長リスト）
    series_list: list[SeriesConfig] = Field(..., min_length=1, max_length=100)
    
    # テンプレート設定
    modality_template: str = Field(..., description="モダリティテンプレート名")
    hospital_template: str | None = Field(None, description="病院テンプレート名")
    device_profile: str | None = Field(None, description="装置のプロファイル名（spec/13）")
    
    # UID生成設定
    uid_method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25"
    uid_custom_root: str | None = Field(None, description="カスタムRoot（custom_root使用時）")
    
    # ピクセルデータ設定
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic
    
    # Transfer Syntax設定
    transfer_syntax: TransferSyntaxConfig
    
    # 文字セット設定
    character_set: CharacterSetConfig
    
    # 異常生成設定
    abnormal: AbnormalConfig = Field(default_factory=AbnormalConfig)

    @model_validator(mode="after")
    def validate_date_consistency(self) -> "GenerationConfig":
        """検査日が生年月日より前でないことを検証する。"""
        # birth_date/study_date は有効な暦日であることもここで検証する
        ...
```

---

## 生成の結果

生成の結果を表すモデルは持たない。`StudyGeneratorService.generate` は、出力の
フォルダの `Path` を返し、失敗は例外（[08_error_handling.md](08_error_handling.md)）
で伝える。進捗は `progress_callback(生成した枚数, 総枚数)` で渡す。

出力のファイル名は `<Patient ID>_<検査日>_<モダリティ>_<連番>.dcm` で、各部分は
`path_safety` で安全な字だけにする。連番のゼロ埋めの桁数は
`max(4, 総出力枚数の桁数)` とする（総出力枚数が 10000 以上なら 5 桁）。

---

## モダリティのダミーのモデル

[12_modality_emulator.md](12_modality_emulator.md) の 5・6 章の値を持つ。
`app/core/models.py` に置き、どれも frozen にする。

```python
class WorklistItem(BaseModel):
    """ワークリストの1件（C-FIND MWL の応答）を読んだ値."""
    key: str                          # 予約の鍵（SHA-1 の先頭 10 桁）。必須
    patient_name: str = ""            # PN をそのまま（成分は = と ^ で区切る）
    patient_id: str = ""
    issuer_of_patient_id: str = ""
    birth_date: str = ""              # Type 2。空を許す
    sex: str = ""                     # Type 2。空を許す
    weight: str = ""                  # DS の文字列（kg）
    size: str = ""                    # DS の文字列（m）
    study_instance_uid: str = ""
    accession_number: str = ""
    referring_physician_name: str = ""
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
    specific_character_set: list[str] = []  # 応答の (0008,0005)
    sequences: dict[str, list[dict]] = {}   # 写す Sequence（DICOM JSON）
    unreadable_attributes: list[str] = []   # 文字コードで戻せなかった属性

class ScheduledPatient(BaseModel):
    """予約から写す患者の値。生年月日・性別の空を許す（Patient とは別）."""
    patient_id: str                   # 1〜16 文字（上限は GenerationConfig と同じ）
    patient_name: str                 # PN の文字列
    issuer_of_patient_id: str = ""
    birth_date: str = ""              # 空 か YYYYMMDD（pattern で検証）
    sex: str = ""                     # 空 か M/F/O（pattern で検証）
    weight: str = ""
    size: str = ""

class ScheduledContext(BaseModel):
    """画像に写す予約の値（予約あり・予約なしの両方）."""
    scheduled: bool                   # False は緊急の患者（予約なし）
    patient: ScheduledPatient
    study_instance_uid: str | None = None  # None ならこの道具が作る
    accession_number: str = ""        # 予約なしは空（長さ0）
    referring_physician_name: str = ""
    study_id: str = ""
    study_description: str = ""
    performed_procedure_step_id: str  # 必須
    institution_name: str = ""        # 空なら病院テンプレートの値のまま
    request_attributes: dict | None = None  # Request Attributes Sequence の1項目（DICOM JSON）
    sequences: dict[str, list[dict]] = {}   # Procedure Code・Issuer of Accession Number・Referenced Study
    specific_character_set: list[str] = []  # 画像の (0008,0005)
    source_ae_title: str = ""         # File Meta (0002,0016)
```

- `GenerationConfig.patient`（`Patient`）は変えない。予約から撮るとき
  `ModalityService` は、生成のための仮の `Patient` を作って
  `GenerationConfig` に入れ、画像の患者の値は `ScheduledContext` で
  上書きする（生年月日が空なら仮の生年月日は検査日にし、画像では
  空にして Patient's Age を出さない）
- `StudyGeneratorService.generate` は `scheduled: ScheduledContext | None`
  を受ける。渡さなければいまと同じ動き

---

## Spatial Coordinates

```python
class SpatialCoordinates(BaseModel):
    """空間座標データ"""
    instance_number: int = Field(..., ge=1)
    image_position_patient: list[float] = Field(..., min_length=3, max_length=3)
    slice_location: float
    
    # オプション（固定値）
    image_orientation_patient: list[float] = Field(
        default=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        min_length=6,
        max_length=6
    )
    pixel_spacing: list[float] = Field(
        default=[0.5, 0.5],
        min_length=2,
        max_length=2
    )
```

---

## Template（テンプレート）と装置のプロファイル

テンプレート（`templates/` の YAML）は、型を付けずに `dict` で扱う。
`TemplateLoaderService` が読み込んでマージし、`StudyGeneratorService` が
`info`・`file_meta` などの欄を読む（欄の定義は [07_job_schema.md](07_job_schema.md)）。

装置のプロファイル（`DeviceProfile`）は、`app/core/device_profile.py` の
Pydantic モデルで型を付けている。定義は [13_device_profiles.md](13_device_profiles.md)
を正本とする。`GenerationConfig.device_profile` はその名前を指す。

---

## 使用例

### Patient生成

```python
from app.core.models import Patient, PatientName

patient = Patient(
    patient_id="P000001",
    patient_name=PatientName(
        alphabetic="YAMADA^TARO",
        ideographic="山田^太郎",
        phonetic="ヤマダ^タロウ"
    ),
    birth_date="19800115",
    sex="M",
    age="044Y",
    weight=65.5,
    size=170.0  # cm
)

# DICOM PN形式に変換
pn_japanese = patient.patient_name.to_dicom_pn(
    use_ideographic=True,
    use_phonetic=True
)
# => "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"

pn_ascii = patient.patient_name.to_dicom_pn(
    use_ideographic=False,
    use_phonetic=False
)
# => "YAMADA^TARO"
```

### GenerationConfig読み込み

```python
import yaml
from app.core.models import GenerationConfig

with open("job.yaml") as f:
    job_dict = yaml.safe_load(f)

config = GenerationConfig(**job_dict)

# Pydanticが自動検証
# - patient_id は16文字以内か
# - birth_date/study_date は有効な暦日か
# - study_date が birth_date 以上か
# - sexはM/F/Oか
# etc.
```

---

## ファイル配置

`app/core/models.py` にすべてのデータモデルを置く。装置のプロファイルのモデルは
`app/core/device_profile.py`、モダリティのダミーの設定のモデルは
`app/modality/config.py` に置く。

---

## バリデーション

### Pydanticの検証

```python
from pydantic import ValidationError

try:
    patient = Patient(
        patient_id="P000001_TOO_LONG_ID",  # 16文字超過
        patient_name=...,
        birth_date="19800115",
        sex="X",  # M/F/O 以外
    )
except ValidationError as e:
    print(e)
    # ValidationError: 2 validation errors for Patient
    #   patient_id
    #     String should have at most 16 characters
    #   sex
    #     String should match pattern '^(M|F|O)$'
```

`Patient` のパターン検証は形（8 桁の数字）だけを見る。暦として有効な日付かと、
検査日が生年月日以降かは、`GenerationConfig` の検証（`validate_date_consistency`）
が行う。

### ファイル名に使う値

Patient ID などの値を検証で禁止文字のある値として断ることはしない。出力の
ファイル名とフォルダ名に使うときに、Core の `path_safety` が決まった字だけに
置き換える（[02_core_engine.md](02_core_engine.md) の「Core のそのほかのモジュール」）。

---

## 関連する文書

- [07_job_schema.md](07_job_schema.md)：Job YAML のスキーマ
- [02_core_engine.md](02_core_engine.md)：モデルを使う Core の処理
