# 07. Job YAMLスキーマ

## 概要

Job YAMLは、DICOM生成の全設定を記述する統一フォーマット。

**用途**:

- CLI: `python -m app.cli generate job.yaml`
- GUI: Job設定のロード・保存
- テストケース: 再現可能な生成設定

---

## スキーマ定義

### 完全な例

```yaml
# job.yaml - DICOM生成設定

# ジョブ基本情報
job_name: "CT検査テストデータ生成"
output_dir: "output/ACC000001"

# 患者情報
patient:
  patient_id: "P000001"
  patient_name:
    alphabetic: "YAMADA^TARO"
    ideographic: "山田^太郎"
    phonetic: "ヤマダ^タロウ"
  birth_date: "19800115"
  sex: "M"
  age: "044Y"
  weight: 65.5
  size: 170.0
  patient_comments: ""

# スタディ情報
study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "143000"
  study_description: "CT CHEST"
  referring_physician_name: "TANAKA^JIRO=田中^次郎=タナカ^ジロウ"
  num_series: 3

# シリーズ情報（リスト）
series_list:
  - series_number: 1
    series_description: "Scanogram"
    num_images: 1
    protocol_name: "SCOUT"
    slice_thickness: 5.0
    slice_spacing: 5.0
    start_z: 0.0
  
  - series_number: 2
    series_description: "Axial Chest"
    num_images: 20
    protocol_name: "CHEST_ROUTINE"
    slice_thickness: 5.0
    slice_spacing: 5.0
    start_z: 0.0
  
  - series_number: 3
    series_description: "Axial Abdomen"
    num_images: 20
    protocol_name: "ABDOMEN_ROUTINE"
    slice_thickness: 5.0
    slice_spacing: 5.0
    start_z: 100.0

# テンプレート設定
modality_template: "fujifilm_scenaria_view_ct"
hospital_template: "hospital_a"  # null or 省略可

# UID生成設定
uid_method: "uuid_2_25"  # または "custom_root"
uid_custom_root: null    # custom_root使用時のみ指定

# ピクセルデータ設定
pixel_spec:
  mode: "ct_realistic"  # または "simple_text"
  width: 512
  height: 512
  pattern: "gradient"  # ct_realisticの場合: gradient, circle, noise
  bits_stored: 12

# Transfer Syntax設定
transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

# 文字セット設定
character_set:
  specific_character_set: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: true
  use_phonetic: true

# 異常生成設定
abnormal:
  level: "none"  # none, mild, moderate, severe
  allow_invalid_sop_uid: false
  invalid_sop_uid_probability: 0.1
```

---

## 最小構成の例

必須項目のみを含む最小Job YAML：

```yaml
# job_minimal.yaml
job_name: "最小テスト"
output_dir: "output/test"

patient:
  patient_id: "P000001"
  patient_name:
    alphabetic: "TEST^PATIENT"
  birth_date: "20000101"
  sex: "M"

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "120000"
  num_series: 1

series_list:
  - series_number: 1
    num_images: 1

modality_template: "fujifilm_scenaria_view_ct"

pixel_spec:
  mode: "simple_text"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: ""
  use_ideographic: false
  use_phonetic: false
```

---

## フィールド詳細

### patient（必須）

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| `patient_id` | string | ○ | 患者ID（16文字以内） | "P000001" |
| `patient_name` | object | ○ | 患者名 | 下記参照 |
| `birth_date` | string | ○ | 生年月日（YYYYMMDD） | "19800115" |
| `sex` | string | ○ | 性別（M/F/O） | "M" |
| `age` | string | - | 年齢入力（nnnY形式、互換用。DICOM出力は birth_date/study_date から日本法基準で算出） | "044Y" |
| `weight` | float | - | 体重（kg） | 65.5 |
| `size` | float | - | 身長（cm） | 170.0 |
| `patient_comments` | string | - | 患者コメント | "" |

#### patient_name（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `alphabetic` | string | ○ | ローマ字（例: "YAMADA^TARO"） |
| `ideographic` | string | - | 漢字（例: "山田^太郎"） |
| `phonetic` | string | - | カナ（例: "ヤマダ^タロウ"） |

### study（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `accession_number` | string | ○ | Accession Number |
| `study_date` | string | ○ | 検査日（YYYYMMDD、birth_date 以上） |
| `study_time` | string | ○ | 検査時刻（HHMMSS） |
| `study_description` | string | - | 検査説明 |
| `referring_physician_name` | string | - | 紹介医名 |
| `num_series` | int | ○ | シリーズ数 |

### series_list（必須、リスト）

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `series_number` | int | ○ | シリーズ番号 | - |
| `series_description` | string | - | シリーズ説明 | null |
| `num_images` | int | ○ | 画像枚数 | - |
| `protocol_name` | string | - | プロトコル名 | null |
| `slice_thickness` | float | - | スライス厚（mm） | 5.0 |
| `slice_spacing` | float | - | スライス間隔（mm） | 5.0 |
| `start_z` | float | - | 開始Z座標（mm） | 0.0 |

### pixel_spec（必須）

#### Simple Textモード

```yaml
pixel_spec:
  mode: "simple_text"
  width: 512          # オプション、デフォルト512
  height: 512         # オプション、デフォルト512
  background_color: 0 # オプション、デフォルト0
  text_color: 255     # オプション、デフォルト255
  font_size: 24       # オプション、デフォルト24
```

#### CT Realisticモード

```yaml
pixel_spec:
  mode: "ct_realistic"
  width: 512          # オプション、デフォルト512
  height: 512         # オプション、デフォルト512
  pattern: "gradient" # gradient, circle, noise
  bits_stored: 12     # 8-16
```

### transfer_syntax（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `uid` | string | ○ | Transfer Syntax UID |
| `name` | string | ○ | 名称 |
| `is_implicit_vr` | bool | ○ | Implicit VRか |
| `is_little_endian` | bool | ○ | Little Endianか |

**よく使う値**:

```yaml
# Implicit VR Little Endian（デフォルト）
transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

# Explicit VR Little Endian
transfer_syntax:
  uid: "1.2.840.10008.1.2.1"
  name: "Explicit VR Little Endian"
  is_implicit_vr: false
  is_little_endian: true
```

### character_set（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `specific_character_set` | string | ○ | Specific Character Set |
| `use_ideographic` | bool | ○ | 漢字を使用するか |
| `use_phonetic` | bool | ○ | カナを使用するか |

**よく使う値**:

```yaml
# 日本語（ASCII + 日本語）
character_set:
  specific_character_set: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: true
  use_phonetic: true

# ASCII only
character_set:
  specific_character_set: ""
  use_ideographic: false
  use_phonetic: false
```

### abnormal（オプション、デフォルト：正常データ）

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `level` | string | - | 異常レベル（none/mild/moderate/severe） | "none" |
| `allow_invalid_sop_uid` | bool | - | SOP UID 0始まり不正を許可 | false |
| `invalid_sop_uid_probability` | float | - | 不正UID生成確率 | 0.1 |

---

## バリデーション

Job YAMLは `GenerationConfig` Pydanticモデルで検証される。

```python
import yaml
from pydantic import ValidationError
from app.core.models import GenerationConfig

with open("job.yaml") as f:
    job_dict = yaml.safe_load(f)

try:
    config = GenerationConfig(**job_dict)
    print("✅ Validation passed")
except ValidationError as e:
    print("❌ Validation failed:")
    print(e)
```

追加で、以下を検証する:

- `birth_date` と `study_date` が実在する暦日であること
- `study_date >= birth_date` であること
- DICOMタグ `(0010,1010) PatientAge` は `birth_date` と `study_date` から自動算出されること

---

## 出力ファイル名

出力ファイル名形式:

`{patient_id}_{study_date}_{modality}_{sequence}.dcm`

連番 `sequence` のルール:

- ゼロ埋め桁数は `max(4, 総出力枚数の桁数)` を使用
- 総出力枚数が 1〜9999 の場合は4桁（`0001`〜`9999`）
- 総出力枚数が 10000〜99999 の場合は5桁（`00001`〜`99999`）
- 総出力枚数が 100000〜 の場合は6桁以上

例:

- `P000001_20240115_CT_0001.dcm`
- `P000001_20240115_CT_1000.dcm`
- `P000001_20240115_CT_00001.dcm`（総出力枚数が10000以上の場合）
- `P000001_20240115_CT_10000.dcm`

---

## CLI使用例

### 基本生成

```bash
python -m app.cli generate job.yaml
```

### デバッグモード

```bash
python -m app.cli generate job.yaml --verbose
```

### 出力ディレクトリ上書き

```bash
python -m app.cli generate job.yaml --output custom_output/
```

---

## GUI使用例

### Job読み込み

```python
# GUIでJobファイルを開く
config = load_job_file("job.yaml")

# フィールドに反映
ui.patient_id_field.setText(config.patient.patient_id)
ui.accession_number_field.setText(config.study.accession_number)
# ...
```

### Job保存

```python
# GUIから設定を収集
config = GenerationConfig(
    job_name=ui.job_name_field.text(),
    output_dir=ui.output_dir_field.text(),
    patient=...,
    study=...,
    # ...
)

# YAML保存
save_job_file("my_job.yaml", config)
```

---

## テストケース例

### test_jobs/normal_ct_japanese.yaml

```yaml
# 正常なCTデータ（日本語）
job_name: "正常CTテストデータ（日本語）"
output_dir: "output/test_normal_ct_ja"

patient:
  patient_id: "P000001"
  patient_name:
    alphabetic: "YAMADA^TARO"
    ideographic: "山田^太郎"
    phonetic: "ヤマダ^タロウ"
  birth_date: "19800115"
  sex: "M"

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "143000"
  num_series: 1

series_list:
  - series_number: 1
    num_images: 10

modality_template: "fujifilm_scenaria_view_ct"
hospital_template: "hospital_a"

pixel_spec:
  mode: "ct_realistic"
  pattern: "gradient"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: true
  use_phonetic: true
```

### test_jobs/abnormal_moderate.yaml

```yaml
# 異常データ（中度）
job_name: "異常CTテストデータ（中度）"
output_dir: "output/test_abnormal_moderate"

patient:
  patient_id: "P999999"
  patient_name:
    alphabetic: "ABNORMAL^TEST"
  birth_date: "19990101"
  sex: "O"

study:
  accession_number: "ACCABNORMAL"
  study_date: "20240115"
  study_time: "000000"
  num_series: 1

series_list:
  - series_number: 1
    num_images: 5

modality_template: "fujifilm_scenaria_view_ct"

pixel_spec:
  mode: "simple_text"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: ""
  use_ideographic: false
  use_phonetic: false

abnormal:
  level: "moderate"
  allow_invalid_sop_uid: true
  invalid_sop_uid_probability: 0.3
```

---

## スキーマ拡張（将来）

Phase 2以降で検討：

- `multi_patient`: 複数患者の一括生成
- `batch`: バッチ処理設定
- `output_format`: ファイル命名規則カスタマイズ
- `compression`: JPEG圧縮設定

---

## 次のステップ

1. [04_cli.md](04_cli.md) でCLI実装を確認
2. [05_gui.md](05_gui.md) でGUI実装を確認
3. Job YAMLを使ったテストケース作成
