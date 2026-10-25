# 03. データモデル

アプリケーション全体で使うデータモデル（Pydantic v2）の型と制約を定める。

## 1. 共通の規則

- `app/core/models.py` にすべてのデータモデルを置く。どのモデルも
  frozen（`model_config = {"frozen": True}`）
- 装置プロファイルのモデルは `app/core/device_profile.py`、モダリティ
  エミュレーターの設定のモデルは `app/modality/config.py` に置く
- この文書のコードは、型と制約を示すために転記したものである。正本は
  `app/core/models.py` で、食い違ったらコードが正しい

## 2. 患者

### 2.1 PatientName

```python
class PatientName(BaseModel):
    alphabetic: str = Field(..., description="ローマ字表記（例: YAMADA^TARO）")
    ideographic: str | None = Field(None, description="漢字表記（例: 山田^太郎）")
    phonetic: str | None = Field(None, description="カナ表記（例: ヤマダ^タロウ）")

    def to_dicom_pn(self, use_ideographic: bool, use_phonetic: bool) -> str: ...
```

`to_dicom_pn` は、3つのコンポーネントグループを `=` で連結した PN の文字列を
返す。`use_ideographic`・`use_phonetic` が False のとき、または値が無いときは、
そのコンポーネントグループを空にする。末尾の空のコンポーネントグループは削除する。

| 入力 | 戻り値 |
|------|--------|
| 3つとも値があり、両方 True | `YAMADA^TARO=山田^太郎=ヤマダ^タロウ` |
| 両方 False | `YAMADA^TARO` |
| 漢字が無く、カナがある | `YAMADA^TARO==ヤマダ^タロウ` |

### 2.2 Patient

```python
class Patient(BaseModel):
    patient_id: str = Field(..., max_length=16, description="患者ID")
    patient_name: PatientName
    birth_date: str = Field(..., pattern=r"^\d{8}$", description="生年月日（YYYYMMDD）")
    sex: str = Field(..., pattern=r"^(M|F|O)$", description="性別")
    age: str | None = Field(None, pattern=r"^\d{3}Y$", description="年齢入力（互換用）")
    weight: float | None = Field(None, ge=0, le=500, description="体重（kg）")
    size: float | None = Field(None, ge=0, le=300, description="身長（cm）")
    patient_comments: str | None = Field(None, max_length=128, description="患者コメント")

    @property
    def size_in_meters(self) -> float | None: ...
```

- `size` は cm で持ち、DICOM に書くときに `size_in_meters`（`size / 100`）で
  m へ換算する（[ADR-0007](../decisions/0007-patient-size-in-centimeters.md)）
- `age` は入力を受け付けるだけで、作成には使わない。Patient's Age は生年月日と
  検査日から算出する（[02_core_engine.md](02_core_engine.md) の 6.2）
- `patient_comments` は入力を受け付けるだけで、画像には書かない
- `birth_date` のパターンは形（8 桁の数字）だけを検証する。暦として有効な日付か
  は `GenerationConfig` が検証する（4.6）

## 3. スタディ・シリーズ・画像

### 3.1 StudyConfig

```python
class StudyConfig(BaseModel):
    accession_number: str = Field(..., max_length=16, description="Accession Number")
    study_date: str = Field(..., pattern=r"^\d{8}$", description="検査日")
    study_time: str = Field(..., pattern=r"^\d{6}$", description="検査時刻")
    study_description: str | None = Field(None, max_length=64, description="検査説明")
    referring_physician_name: str | None = Field(None, description="紹介医名")
    num_series: int = Field(..., ge=1, le=100, description="シリーズ数")
```

`num_series` は検証するだけで、作成するシリーズの数は
`GenerationConfig.series_list` の件数で決まる。

### 3.2 SeriesConfig

```python
class SeriesConfig(BaseModel):
    series_number: int = Field(..., ge=1, description="シリーズ番号")
    series_description: str | None = Field(None, max_length=64, description="シリーズ説明")
    num_images: int = Field(..., ge=1, le=10000, description="画像枚数")
    protocol_name: str | None = Field(None, description="プロトコル名")
    slice_thickness: float = Field(5.0, gt=0, description="スライス厚（mm）")
    slice_spacing: float = Field(5.0, gt=0, description="スライス間隔（mm）")
    start_z: float = Field(0.0, description="開始Z座標（mm）")
```

撮影のルーチン（[ADR-0025](../decisions/0025-exam-routines.md)）のシリーズは、
次の欄も持つ（`app/core/models.py`）。手で入れたシリーズは既定の値のまま。

| 欄 | 型 | 既定 | 中身 |
|----|----|------|------|
| `kind` | `axial`・`localizer`・`coronal`・`sagittal`・`dose_report`、MR は `localizer`・`acquisition`・`derived` | `axial` | シリーズの種類（spec/06 の 5.1・5.2） |
| `views` | `frontal`・`lateral` の並び | `["frontal"]` | 位置決めの画像ごとの方向。足りなければ繰り返す |
| `contrast` | bool | false | 造影のシリーズ |
| `modality` | `CT`・`MR`・None | None | このシリーズのモダリティ。None はテンプレートのモダリティ（[ADR-0028](../decisions/0028-mr-images.md)） |
| `plane` | `axial`・`sagittal`・`coronal`・`three_plane` | `axial` | MR の断面。`three_plane` は画像を3等分して axial・coronal・sagittal の順にする |
| `sequence` | `SE`・`IR`・`GR`・`EP` | `SE` | MR の Scanning Sequence |
| `acquisition_type` | `2D`・`3D` | `2D` | MR Acquisition Type |

`kind` が `acquisition`・`derived` のシリーズは `modality` を MR にする（CT のシリーズ
に MR の種類を入れると検証で止まる）。MR のテンプレートで手で入れたシリーズは、
種類が `axial` なら MR の撮像（`acquisition`）にする。

ルーチンそのもの（`templates/routine/` の YAML）は `app/core/routine.py` の
`Routine` で読む。形はモダリティごとに違う（CT はシリーズの種類と再構成、MR は
シーケンス、CR・DX は撮影の方向、US は静止画と動画の数）。どのシリーズも `images`
（既定の画像数）を必ず持つ。MR のシリーズは、断面 `plane`、スライス厚 `slice_thickness`、
すきま `spacing`（画像の間隔は スライス厚 + すきま）、`sequence`、`acquisition_type`
を持つ。

### 3.3 InstanceConfig

```python
class InstanceConfig(BaseModel):
    instance_number: int = Field(..., ge=1, description="インスタンス番号")
    acquisition_number: int = Field(1, ge=1, description="Acquisition Number")
```

### 3.4 UIDContext

```python
class UIDContext(BaseModel):
    study_instance_uid: str
    frame_of_reference_uid: str
    implementation_class_uid: str
    instance_creator_uid: str
```

Study 単位で共通の UID を持つ。Series Instance UID と SOP Instance UID は
画像ごとに作成するので含めない。

### 3.5 SpatialCoordinates

```python
class SpatialCoordinates(BaseModel):
    instance_number: int = Field(..., ge=1)
    image_position_patient: list[float] = Field(..., min_length=3, max_length=3)
    slice_location: float
    image_orientation_patient: list[float] = Field(
        default=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0], min_length=6, max_length=6
    )
    pixel_spacing: list[float] = Field(default=[0.5, 0.5], min_length=2, max_length=2)
```

`SpatialCalculator` は `image_orientation_patient` と `pixel_spacing` を
設定しないので、どちらも既定値になる。

## 4. 作成の設定

### 4.1 PixelSpec

```python
class PixelSpecSimple(BaseModel):
    mode: Literal["simple_text"] = "simple_text"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    background_color: int = Field(0, ge=0, le=255)
    text_color: int = Field(255, ge=0, le=255)
    font_size: int = Field(24, ge=8, le=72)

class PixelSpecCTRealistic(BaseModel):
    mode: Literal["ct_realistic"] = "ct_realistic"
    width: int = Field(512, ge=64, le=4096)
    height: int = Field(512, ge=64, le=4096)
    pattern: Literal["gradient", "circle", "noise"] = "gradient"
    bits_stored: int = Field(12, ge=12, le=16)  # CT は 12〜16（PS3.3 C.8.2.1.1.5）

PixelSpec = PixelSpecSimple | PixelSpecCTRealistic
```

- `PixelSpecSimple` の `background_color`・`text_color`・`font_size` は検証する
  だけで、作成には使わない。Simple Text は黒の背景・白の文字・16 ポイントで
  描画する（[02_core_engine.md](02_core_engine.md) の 3.1）
- Simple Text の画像は Bits Stored 12 で書く

### 4.2 TransferSyntaxConfig

```python
class TransferSyntaxConfig(BaseModel):
    uid: str = Field("1.2.840.10008.1.2", description="Transfer Syntax UID")
    name: str = Field("Implicit VR Little Endian", description="名称")
    is_implicit_vr: bool = Field(True, description="Implicit VR か")
    is_little_endian: bool = Field(True, description="Little Endian か")
```

作成で使うのは `uid` だけ。作成できる値は [02_core_engine.md](02_core_engine.md)
の 6.2 にある。

### 4.3 CharacterSetConfig

```python
class CharacterSetConfig(BaseModel):
    specific_character_set: str = Field(
        r"ISO 2022 IR 6\ISO 2022 IR 87", description="Specific Character Set"
    )
    use_ideographic: bool = Field(True, description="漢字を使用するか")
    use_phonetic: bool = Field(True, description="カナを使用するか")
```

テンプレートの `character_set.specific_character_set` と
`patient_module.patient_name.use_ideographic`・`use_phonetic` があれば、
そちらが優先される（[07_job_schema.md](07_job_schema.md)）。

### 4.4 AbnormalConfig

```python
class AbnormalConfig(BaseModel):
    level: Literal["none", "mild", "moderate", "severe"] = "none"
    allow_invalid_sop_uid: bool = Field(False, description="SOP UID 0始まり不正を許可")
    invalid_sop_uid_probability: float = Field(0.1, ge=0.0, le=1.0, description="不正UID生成確率")
```

`invalid_sop_uid_probability` は検証するだけで、作成には使わない。
0 始まりの SOP Instance UID の確率は 10% に固定している
（[02_core_engine.md](02_core_engine.md) の 2.1）。

### 4.5 GenerationConfig

Job YAML から読み込む、作成の全体の設定。

```python
class GenerationConfig(BaseModel):
    job_name: str = Field(..., description="ジョブ名")
    output_dir: str = Field(..., description="出力ディレクトリ")
    patient: Patient
    study: StudyConfig
    series_list: list[SeriesConfig] = Field(..., min_length=1, max_length=100)
    modality_template: str = Field(..., description="モダリティテンプレート名")
    hospital_template: str | None = Field(None, description="病院テンプレート名")
    device_profile: str | None = Field(None, description="装置のプロファイル名")
    uid_method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25"
    uid_custom_root: str | None = Field(None, description="カスタムRoot")
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic
    transfer_syntax: TransferSyntaxConfig
    character_set: CharacterSetConfig
    abnormal: AbnormalConfig = Field(default_factory=AbnormalConfig)

    @model_validator(mode="after")
    def validate_date_consistency(self) -> GenerationConfig: ...
```

`device_profile` は [13_device_profiles.md](13_device_profiles.md) の装置
プロファイルの名前を指す。

### 4.6 検証

`validate_date_consistency` は次を検証する。

| 条件 | エラーの種類 |
|------|--------------|
| `patient.birth_date` と `study.study_date` が暦として有効な日付 | `invalid_calendar_date` |
| `study.study_date` が `patient.birth_date` 以降 | `invalid_date_order` |

Patient ID などの値を、禁止文字のある値として検証で拒否することはしない。出力の
ファイル名とフォルダ名に使うときに、Core の `path_safety` が決まった文字だけに
置き換える（[02_core_engine.md](02_core_engine.md) の 8 章）。

## 5. 作成の結果

作成の結果を表すモデルは持たない。`StudyGeneratorService.generate` は、出力の
フォルダの `Path` を返し、失敗は例外（[08_error_handling.md](08_error_handling.md)）
で伝える。進捗は `progress_callback(作成した枚数, 総枚数)` で渡す。

出力のファイル名は `<Patient ID>_<検査日>_<モダリティ>_<連番>.dcm` で、各部分は
`path_safety` で安全な文字だけにする。連番のゼロ埋めの桁数は
`max(4, 総出力枚数の桁数)` とする（総出力枚数が 10000 以上なら 5 桁）。

## 6. モダリティエミュレーターのモデル

[12_modality_emulator.md](12_modality_emulator.md) の 5・6 章の値を持つ。
`app/core/models.py` に置き、どれも frozen にする。

```python
class WorklistItem(BaseModel):
    """ワークリストの1件（C-FIND MWL の応答）を読んだ値."""
    key: str                          # 予約のキー（SHA-1 の先頭 10 桁）。必須
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
    sequences: dict[str, list[dict]] = {}   # 転記する Sequence（DICOM JSON）
    unreadable_attributes: list[str] = []   # 文字コードで復元できなかった属性

class ScheduledPatient(BaseModel):
    """予約から転記する患者の値。生年月日・性別の空を許す（Patient とは別）."""
    patient_id: str                   # 1〜16 文字（上限は Patient と同じ）
    patient_name: str                 # PN の文字列
    issuer_of_patient_id: str = ""
    birth_date: str = ""              # 空 か YYYYMMDD（pattern で検証）
    sex: str = ""                     # 空 か M/F/O（pattern で検証）
    weight: str = ""
    size: str = ""

class ScheduledContext(BaseModel):
    """画像に転記する予約の値（予約あり・予約なしの両方）."""
    scheduled: bool                   # False は緊急の患者（予約なし）
    patient: ScheduledPatient
    study_instance_uid: str | None = None  # None なら DTG が作る
    accession_number: str = ""        # 予約なしは空（長さ0）
    referring_physician_name: str = ""
    study_id: str = ""
    study_description: str = ""
    performed_procedure_step_id: str  # 必須
    performed_procedure_step_sop_instance_uid: str = ""  # MPPS の SOP Instance UID
    institution_name: str = ""        # 空なら病院テンプレートの値のまま
    request_attributes: dict | None = None  # Request Attributes Sequence の1項目（DICOM JSON）
    sequences: dict[str, list[dict]] = {}   # Procedure Code・Issuer of Accession Number・Referenced Study
    specific_character_set: list[str] = []  # 画像の (0008,0005)
    source_ae_title: str = ""         # File Meta (0002,0016)
```

- `performed_procedure_step_sop_instance_uid` は、MPPS を使うときの MPPS の
  SOP Instance UID。画像の Referenced Performed Procedure Step Sequence に
  転記する（IHE RAD TF-2x A.1.3・A.2.2）
- `GenerationConfig.patient`（`Patient`）は変えない。予約から撮影するとき
  `ModalityService` は、作成のための仮の `Patient` を作成して
  `GenerationConfig` に入れ、画像の患者の値は `ScheduledContext` で
  上書きする（生年月日が空なら仮の生年月日は検査日にし、画像では
  空にして Patient's Age を出力しない）
- `StudyGeneratorService.generate` は `scheduled: ScheduledContext | None`
  を受け取る。渡さなければ予約の値を転記しない

## 7. テンプレートと装置プロファイル

テンプレート（`templates/` の YAML）は、型を付けずに `dict` で扱う。
`TemplateLoaderService` が読み込んでマージし、`StudyGeneratorService` が
`info`・`file_meta` などのフィールドを読む（フィールドの定義は
[07_job_schema.md](07_job_schema.md)）。

装置プロファイル（`DeviceProfile`）は、`app/core/device_profile.py` の
Pydantic モデルで型を付けている。定義は [13_device_profiles.md](13_device_profiles.md)
を正本とする。

## 8. 関連する文書

- [07_job_schema.md](07_job_schema.md)：Job YAML のスキーマ
- [02_core_engine.md](02_core_engine.md)：モデルを使う Core の処理
