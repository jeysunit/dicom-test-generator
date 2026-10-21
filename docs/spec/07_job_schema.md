# 07. Job YAML スキーマ

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 概要

Job YAMLは、DICOM生成の全設定を記述する統一フォーマット。

**用途**:

- CLI: `python -m app.cli generate job.yaml`
- テストケース: 再現可能な生成設定

Job YAML は CLI だけが読む。PySide6 の画面（spec/05）は Job YAML の読み込み・保存を持たない。
実体は `app/core/models.py` の `GenerationConfig`（Pydantic）で、この文書と食い違えば models.py が正本。
実例は `examples/` にある（`job_minimal.yaml`・`job_full.yaml`・`job_acc000003.yaml`）。

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
modality_template: "ct_generic"
hospital_template: "hospital_a"  # null or 省略可
device_profile: "dtg_synthetic_ct"  # 装置のプロファイル。null or 省略可（spec/13）

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

modality_template: "ct_generic"

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

### 最上位

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `job_name` | string | ○ | ジョブ名 | - |
| `output_dir` | string | ○ | 出力ディレクトリ（`--output` で上書き） | - |
| `patient` | object | ○ | 下記 | - |
| `study` | object | ○ | 下記 | - |
| `series_list` | list | ○ | 1〜100 件 | - |
| `modality_template` | string | ○ | `templates/modality/` のテンプレート名 | - |
| `hospital_template` | string | - | `templates/hospital/` のテンプレート名 | null |
| `device_profile` | string | - | 装置プロファイル名（`--profile` で上書き。[13_device_profiles.md](13_device_profiles.md)） | null |
| `uid_method` | string | - | `uuid_2_25` / `custom_root` | "uuid_2_25" |
| `uid_custom_root` | string | - | `custom_root` のときの UID の根 | null |
| `pixel_spec` | object | ○ | 下記 | - |
| `transfer_syntax` | object | ○ | 下記 | - |
| `character_set` | object | ○ | 下記 | - |
| `abnormal` | object | - | 下記 | 正常データ |

### patient（必須）

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| `patient_id` | string | ○ | 患者ID（16文字以内） | "P000001" |
| `patient_name` | object | ○ | 患者名 | 下記参照 |
| `birth_date` | string | ○ | 生年月日（YYYYMMDD） | "19800115" |
| `sex` | string | ○ | 性別（M/F/O） | "M" |
| `age` | string | - | 年齢入力（nnnY形式、互換用。DICOM出力は birth_date/study_date から日本法基準で算出） | "044Y" |
| `weight` | float | - | 体重（kg、0〜500） | 65.5 |
| `size` | float | - | 身長（cm、0〜300。DICOM の Patient's Size にはメートルで書く） | 170.0 |
| `patient_comments` | string | - | 患者コメント（128文字以内） | "" |

#### patient_name（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `alphabetic` | string | ○ | ローマ字（例: "YAMADA^TARO"） |
| `ideographic` | string | - | 漢字（例: "山田^太郎"） |
| `phonetic` | string | - | カナ（例: "ヤマダ^タロウ"） |

### study（必須）

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `accession_number` | string | ○ | Accession Number（16文字以内） |
| `study_date` | string | ○ | 検査日（YYYYMMDD、birth_date 以上） |
| `study_time` | string | ○ | 検査時刻（HHMMSS） |
| `study_description` | string | - | 検査説明（64文字以内） |
| `referring_physician_name` | string | - | 紹介医名 |
| `num_series` | int | ○ | シリーズ数（1〜100） |

### series_list（必須、リスト）

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `series_number` | int | ○ | シリーズ番号（1以上） | - |
| `series_description` | string | - | シリーズ説明（64文字以内） | null |
| `num_images` | int | ○ | 画像枚数（1〜10000） | - |
| `protocol_name` | string | - | プロトコル名 | null |
| `slice_thickness` | float | - | スライス厚（mm、0より大きい） | 5.0 |
| `slice_spacing` | float | - | スライス間隔（mm、0より大きい） | 5.0 |
| `start_z` | float | - | 開始Z座標（mm） | 0.0 |

### pixel_spec（必須）

`mode` で2つの形に分かれる。`mode` は省略できない。

#### Simple Textモード

```yaml
pixel_spec:
  mode: "simple_text"
  width: 512          # オプション、デフォルト512（64〜4096）
  height: 512         # オプション、デフォルト512（64〜4096）
  background_color: 0 # オプション、デフォルト0（0〜255）
  text_color: 255     # オプション、デフォルト255（0〜255）
  font_size: 24       # オプション、デフォルト24（8〜72）
```

#### CT Realisticモード

```yaml
pixel_spec:
  mode: "ct_realistic"
  width: 512          # オプション、デフォルト512（64〜4096）
  height: 512         # オプション、デフォルト512（64〜4096）
  pattern: "gradient" # gradient, circle, noise
  bits_stored: 12     # 12-16（CT。PS3.3 C.8.2.1.1.5）
```

`bits_stored` の下限は 12。8〜11 は検証エラー（終了コード 4）になるので、
古い Job YAML は 12 以上に修正する。

### transfer_syntax（必須）

セクション自体は必須で、中のフィールドはすべて省略できる（省略すると Implicit VR Little Endian）。

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `uid` | string | - | Transfer Syntax UID | "1.2.840.10008.1.2" |
| `name` | string | - | 名称 | "Implicit VR Little Endian" |
| `is_implicit_vr` | bool | - | Implicit VRか | true |
| `is_little_endian` | bool | - | Little Endianか | true |

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

セクション自体は必須で、中のフィールドはすべて省略できる（省略すると日本語を使う設定）。

| フィールド | 型 | 必須 | 説明 | デフォルト |
|-----------|-----|------|------|----------|
| `specific_character_set` | string | - | Specific Character Set | "ISO 2022 IR 6\\ISO 2022 IR 87" |
| `use_ideographic` | bool | - | 漢字を使用するか | true |
| `use_phonetic` | bool | - | カナを使用するか | true |

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
| `level` | string | - | 異常レベル（none/mild/moderate/severe）。画像に適用される（[02](02_core_engine.md)）。`generate --abnormal-level` で上書きできる。ほかの値は検証エラーになる | "none" |
| `allow_invalid_sop_uid` | bool | - | SOP UID 0始まり不正を許可 | false |
| `invalid_sop_uid_probability` | float | - | 不正UID生成確率（0.0〜1.0） | 0.1 |

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

### 装置プロファイルの上書き

```bash
python -m app.cli generate job.yaml --profile dtg_synthetic_ct
```

---

## テストケース例

以下は、テストやローカルでの確認に使える Job YAML の例である（リポジトリには置いていない）。

### normal_ct_japanese.yaml

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

modality_template: "ct_generic"
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

### abnormal_moderate.yaml

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

modality_template: "ct_generic"

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

## 関連文書

- [04_cli.md](04_cli.md): Job YAML を読むコマンド
- [13_device_profiles.md](13_device_profiles.md): `device_profile`
