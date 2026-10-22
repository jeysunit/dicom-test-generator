# 07. Job YAML のスキーマ

Job YAML の形式を定める。Job YAML は 1 回の DICOM の作成の設定を 1 つの
ファイルに書いたもので、CLI の `generate` と `validate` が読む（spec/04）。

## 1. 概要

- 実体は `app/core/models.py` の `GenerationConfig`（Pydantic）で、この文書と
  食い違えば models.py が正本
- PySide6 の画面（spec/05）は Job YAML の読み込み・保存を持たない
- 実例は `examples/` にある（`job_minimal.yaml`・`job_full.yaml`・
  `job_acc000003.yaml`）
- 作成される DICOM の値の規則は [06_dicom_rules.md](06_dicom_rules.md) にある

## 2. 例

### 2.1 すべての項目を書いた例

```yaml
job_name: "CT検査テストデータ生成"
output_dir: "output/ACC000001"

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

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "143000"
  study_description: "CT CHEST"
  referring_physician_name: "TANAKA^JIRO=田中^次郎=タナカ^ジロウ"
  num_series: 3

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

modality_template: "ct_generic"
hospital_template: "hospital_a"
device_profile: "dtg_synthetic_ct"

uid_method: "uuid_2_25"
uid_custom_root: null

pixel_spec:
  mode: "ct_realistic"
  width: 512
  height: 512
  pattern: "gradient"
  bits_stored: 12

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: true
  use_phonetic: true

abnormal:
  level: "none"
  allow_invalid_sop_uid: false
  invalid_sop_uid_probability: 0.1
```

### 2.2 必須の項目だけの例

`transfer_syntax` と `character_set` は、中の項目を省略しても節そのものは
必須である。

```yaml
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

character_set:
  specific_character_set: ""
  use_ideographic: false
  use_phonetic: false
```

## 3. 項目

「必須」の ○ は省略できない項目。定義に無いキーは無視する。

### 3.1 最上位

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `job_name` | string | ○ | ジョブ名。ログに出力する | - |
| `output_dir` | string | ○ | 出力ディレクトリ（`--output` で上書き） | - |
| `patient` | object | ○ | 3.2 | - |
| `study` | object | ○ | 3.4 | - |
| `series_list` | list | ○ | 1〜100 件。3.5 | - |
| `modality_template` | string | ○ | `templates/modality/` のテンプレート名 | - |
| `hospital_template` | string | - | `templates/hospital/` のテンプレート名 | null |
| `device_profile` | string | - | 装置プロファイル名（`--profile` で上書き。[13_device_profiles.md](13_device_profiles.md)） | null |
| `uid_method` | string | - | `uuid_2_25` / `custom_root`（spec/06 の 3 章） | `uuid_2_25` |
| `uid_custom_root` | string | - | `custom_root` のときの UID のルート | null |
| `pixel_spec` | object | ○ | 3.6 | - |
| `transfer_syntax` | object | ○ | 3.7 | - |
| `character_set` | object | ○ | 3.8 | - |
| `abnormal` | object | - | 3.9 | 正常のデータ |

### 3.2 patient

| フィールド | 型 | 必須 | 説明 | 例 |
|-----------|-----|------|------|-----|
| `patient_id` | string | ○ | 患者 ID（16 文字以内） | `"P000001"` |
| `patient_name` | object | ○ | 患者名（3.3） | - |
| `birth_date` | string | ○ | 生年月日（YYYYMMDD。実在する日付） | `"19800115"` |
| `sex` | string | ○ | 性別（`M` / `F` / `O`） | `"M"` |
| `age` | string | - | 年齢（`nnnY` の形式）。受け付けるが使わない。Patient's Age は `birth_date` と `study_date` から算出する（spec/06 の 8 章） | `"044Y"` |
| `weight` | float | - | 体重（kg、0〜500） | 65.5 |
| `size` | float | - | 身長（cm、0〜300。Patient's Size にはメートルで書く） | 170.0 |
| `patient_comments` | string | - | 患者コメント（128 文字以内）。受け付けるが DICOM には書かない | `""` |

### 3.3 patient.patient_name

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `alphabetic` | string | ○ | 英字（例：`YAMADA^TARO`） |
| `ideographic` | string | - | 漢字（例：`山田^太郎`） |
| `phonetic` | string | - | かな（例：`ヤマダ^タロウ`） |

PN への組み立ては spec/06 の 7.2 にある。

### 3.4 study

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `accession_number` | string | ○ | Accession Number（16 文字以内） |
| `study_date` | string | ○ | 検査日（YYYYMMDD。実在する日付で、`birth_date` 以後） |
| `study_time` | string | ○ | 検査時刻（HHMMSS） |
| `study_description` | string | - | 検査の説明（64 文字以内） |
| `referring_physician_name` | string | - | 紹介医名（PN の形式） |
| `num_series` | int | ○ | シリーズ数（1〜100）。`series_list` の件数とは照合しない。作成するシリーズは `series_list` で決まる |

### 3.5 series_list

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `series_number` | int | ○ | シリーズ番号（1 以上） | - |
| `series_description` | string | - | シリーズの説明（64 文字以内） | null |
| `num_images` | int | ○ | 画像の枚数（1〜10000） | - |
| `protocol_name` | string | - | プロトコル名 | null |
| `slice_thickness` | float | - | スライス厚（mm、0 より大きい） | 5.0 |
| `slice_spacing` | float | - | スライス間隔（mm、0 より大きい） | 5.0 |
| `start_z` | float | - | 開始の z 座標（mm） | 0.0 |

空間座標の計算は spec/06 の 6 章にある。

### 3.6 pixel_spec

`mode` で 2 つの形に分かれる。`mode` は省略できない。画素の規則は spec/06 の
4 章にある。

`mode: "simple_text"`

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `width` | int | - | 幅（64〜4096） | 512 |
| `height` | int | - | 高さ（64〜4096） | 512 |
| `background_color` | int | - | 0〜255。受け付けるが画像には反映しない | 0 |
| `text_color` | int | - | 0〜255。受け付けるが画像には反映しない | 255 |
| `font_size` | int | - | 8〜72。受け付けるが画像には反映しない | 24 |

`mode: "ct_realistic"`

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `width` | int | - | 幅（64〜4096） | 512 |
| `height` | int | - | 高さ（64〜4096） | 512 |
| `pattern` | string | - | `gradient` / `circle` / `noise` | `gradient` |
| `bits_stored` | int | - | 12〜16（CT。PS3.3 C.8.2.1.1.5）。範囲の外は検証のエラー | 12 |

### 3.7 transfer_syntax

節そのものは必須で、中の項目はすべて省略できる（省略すると Implicit VR
Little Endian）。作成できる UID は spec/06 の 9 章にある。

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `uid` | string | - | Transfer Syntax UID | `1.2.840.10008.1.2` |
| `name` | string | - | 名称。作成には使わない | `Implicit VR Little Endian` |
| `is_implicit_vr` | bool | - | Implicit VR か。作成には使わない（UID から決まる） | true |
| `is_little_endian` | bool | - | Little Endian か。作成には使わない（UID から決まる） | true |

### 3.8 character_set

節そのものは必須で、中の項目はすべて省略できる（省略すると日本語を使う設定）。
病院テンプレート・装置プロファイルとの優先順位は spec/06 の 7 章にある。

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `specific_character_set` | string | - | Specific Character Set。複数の値は `\` で区切る | `ISO 2022 IR 6\ISO 2022 IR 87` |
| `use_ideographic` | bool | - | 患者名に漢字を書くか | true |
| `use_phonetic` | bool | - | 患者名にかなを書くか | true |

### 3.9 abnormal

省略すると正常のデータを作成する。

| フィールド | 型 | 必須 | 説明 | 既定値 |
|-----------|-----|------|------|--------|
| `level` | string | - | 異常のレベル（`none` / `mild` / `moderate` / `severe`）。画像に適用する（[02](02_core_engine.md)）。`generate --abnormal-level` で上書きできる。ほかの値は検証のエラー | `none` |
| `allow_invalid_sop_uid` | bool | - | SOP Instance UID に先頭が 0 の成分を含む値を混ぜる（spec/06 の 3.4） | false |
| `invalid_sop_uid_probability` | float | - | 0.0〜1.0。受け付けるが使わない（確率は 10% で固定） | 0.1 |

## 4. 検証

- CLI は、`--output`・`--profile`・`--abnormal-level` の値を Job YAML に
  反映してから、`GenerationConfig` で検証する
- 3 章の型・範囲・形式のほか、次を検証する
  - `birth_date` と `study_date` が実在する日付であること
  - `study_date` が `birth_date` 以後であること
- 検証のエラーは CLI の終了コード 4（spec/08 の 3 章）。YAML として読めない
  ファイルや、最上位がマッピングでないファイルは終了コード 2、存在しない
  ファイルは終了コード 3

## 5. 出力ファイル名

形式は `{patient_id}_{study_date}_{modality}_{連番}.dcm`。

- `modality` はモダリティテンプレートの `info.modality`（無ければ `CT`）
- 各部分は、ファイル名に使える文字だけにしてから使う（spec/12 の 6.5）
- 連番は 1 回の作成の中で、シリーズをまたいで 1 から数える
- 連番のゼロ埋めの桁数は `max(4, 総出力枚数の桁数)`。総出力枚数が 1〜9999
  なら 4 桁（`0001`〜`9999`）、10000〜99999 なら 5 桁、100000 以上なら 6 桁
  以上

例：

- `P000001_20240115_CT_0001.dcm`
- `P000001_20240115_CT_00001.dcm`（総出力枚数が 10000 以上のとき）

## 6. 関連文書

- [04_cli.md](04_cli.md)：Job YAML を読むコマンド
- [06_dicom_rules.md](06_dicom_rules.md)：作成する DICOM の規則
- [13_device_profiles.md](13_device_profiles.md)：`device_profile`
