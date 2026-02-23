# 03. データモデル定義

## 概要

このドキュメントでは、アプリケーション全体で使用するデータモデル（Pythonクラス）を定義する。

**実装方針**:

- **Pydantic v2** を使用（型検証・シリアライズ）
- Immutable推奨（`frozen=True`）
- 明確なデフォルト値

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
```

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
    mode: str = Field("simple_text", const=True)
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    background_color: int = Field(0, ge=0, le=255)
    text_color: int = Field(255, ge=0, le=255)
    font_size: int = Field(24, ge=8, le=72)

class PixelSpecCTRealistic(BaseModel):
    """CT Realisticモードピクセル設定"""
    mode: str = Field("ct_realistic", const=True)
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    pattern: str = Field("gradient", pattern=r"^(gradient|circle|noise)$")
    bits_stored: int = Field(12, ge=8, le=16)

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
    level: str = Field("none", pattern=r"^(none|mild|moderate|severe)$")
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
    
    # UID生成設定
    uid_method: str = Field("uuid_2_25", pattern=r"^(uuid_2_25|custom_root)$")
    uid_custom_root: str | None = Field(None, description="カスタムRoot（custom_root使用時）")
    
    # ピクセルデータ設定
    pixel_spec: PixelSpec
    
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

## Generation Result（生成結果）

```python
from datetime import datetime

class GeneratedFileInfo(BaseModel):
    """生成ファイル情報"""
    filepath: str
    patient_id: str
    study_uid: str
    series_uid: str
    sop_uid: str
    instance_number: int
    file_size_bytes: int

class GenerationResult(BaseModel):
    """生成結果"""
    success: bool
    total_files: int
    generated_files: list[GeneratedFileInfo]
    failed_files: list[str] = Field(default_factory=list)
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    output_dir: str
    error_message: str | None = None
    
    @property
    def success_rate(self) -> float:
        """成功率を計算"""
        if self.total_files == 0:
            return 0.0
        return len(self.generated_files) / self.total_files
```

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

## Template（テンプレート）

```python
class TemplateInfo(BaseModel):
    """テンプレート情報"""
    name: str
    manufacturer: str
    model_name: str
    modality: str
    version: str
    description: str

# テンプレート本体はdictで扱う（YAMLそのまま）
# 型付けは Phase 2 以降で検討
```

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
    size=1.70
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

### GenerationResult作成

```python
from datetime import datetime
from app.core.models import GenerationResult, GeneratedFileInfo

result = GenerationResult(
    success=True,
    total_files=41,
    generated_files=[
        GeneratedFileInfo(
            filepath="output/P000001_20240115_CT_0001.dcm",
            patient_id="P000001",
            study_uid="2.25.123...",
            series_uid="2.25.456...",
            sop_uid="2.25.789...",
            instance_number=1,
            file_size_bytes=262656
        ),
        # ...
    ],
    failed_files=[],
    start_time=datetime.now(),
    end_time=datetime.now(),
    duration_seconds=5.2,
    output_dir="output/ACC000001"
)

print(f"Success Rate: {result.success_rate * 100:.1f}%")
```

`GeneratedFileInfo.filepath` の連番ルール:

- ゼロ埋め桁数は `max(4, 総出力枚数の桁数)` を使用
- 例: 総出力枚数が10000以上なら `00001` 形式

---

## ファイル配置

```text
app/core/models.py
```

すべてのデータモデルを1ファイルに集約（Phase 0）。

Phase 2以降、必要に応じて分割可能：

```text
app/core/models/
├── __init__.py
├── patient.py
├── study.py
├── generation.py
└── spatial.py
```

---

## バリデーション

### Pydanticの検証

```python
from pydantic import ValidationError

try:
    patient = Patient(
        patient_id="P000001_TOO_LONG_ID",  # 16文字超過
        patient_name=...,
        birth_date="20240199",  # 不正な日付
        sex="X",  # M/F/O 以外
        ...
    )
except ValidationError as e:
    print(e)
    # ValidationError: 3 validation errors for Patient
    #   patient_id
    #     String should have at most 16 characters
    #   birth_date
    #     String should match pattern '^\\d{8}$'
    #   sex
    #     String should match pattern '^(M|F|O)$'
```

### カスタムバリデーション

```python
from pydantic import field_validator

class Patient(BaseModel):
    patient_id: str
    # ...
    
    @field_validator('patient_id')
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        # 禁止文字チェック
        forbidden_chars = ['\\', '/', ':', '*', '?', '<', '>', '|', '.', '"']
        if any(c in v for c in forbidden_chars):
            raise ValueError(f"patient_id contains forbidden characters")
        return v
```

---

## シリアライズ

### JSON出力

```python
config = GenerationConfig(...)
json_str = config.model_dump_json(indent=2)

# ファイル保存
with open("config.json", "w") as f:
    f.write(json_str)
```

### YAML出力

```python
import yaml

config = GenerationConfig(...)
config_dict = config.model_dump()

with open("config.yaml", "w") as f:
    yaml.safe_dump(config_dict, f, allow_unicode=True)
```

---

## 次のステップ

1. [07_job_schema.md](07_job_schema.md) で Job YAML スキーマを確認
2. データモデル実装（`app/core/models.py`）
3. Core Engine実装で使用
