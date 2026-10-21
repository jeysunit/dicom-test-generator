# 06. DICOM医療仕様

## 概要

このドキュメントでは、医療DICOMの詳細仕様を定義する。

**重要**: この道具は DICOM と HL7（v2・FHIR）の規格に違反しないことを
開発の前提とする。この仕様の値・Type・長さ・文字コードは、原典
（dicom.nema.org の PS3.x。IHE の Technical Framework）で確かめ、
規格の節番号を書く。仕様を変えるときも原典に合わせる。

### ふつうの経路と異常のデータの経路

この道具は、あえて DICOM の規格に違反したデータを作る機能（異常のデータ）を
持つ。規格に違反しない前提は、ふつうの経路だけに掛かる（2026-10-21 に
承認者が決めた）。

- **ふつうの経路**：異常のデータのレベルが `none` で、
  `abnormal.allow_invalid_sop_uid` を使わない生成。Job・テンプレート・
  装置のプロファイル・予約・画面と CLI の入力は、規格に合う値だけを受け、
  合わない値は生成の前に断る。作る画像は規格どおりにする
- **異常のデータの経路**：`abnormal.level` が `mild`・`moderate`・`severe`
  のときと、`abnormal.allow_invalid_sop_uid`。規格に違反した値を作ること
  そのものが目的で、規格の前提の対象外。何を壊すかの約束は
  [spec/02 の AbnormalGenerator](02_core_engine.md)（壊すタグの表・
  Pixel Data の削除・SOP Instance UID の 0 始まり）で、この約束にある
  壊し方は、ふつうの経路の確かめで狭めない
- 異常のデータは、組み終えた Dataset に最後に当てる（spec/02）。
  ふつうの経路の確かめ（Type 1 の属性・画素の範囲・DS の長さ・UID の形・
  文字コード・入力の `\`）は、その前の値か、約束に無い入力に掛かるので、
  約束の壊し方とぶつからない
- 約束に無い違反（例：廃止の転送の形 Explicit VR Big Endian）は、
  異常のデータの経路でも作らない。作れるようにするときは、先に spec/02 の
  約束に足す

### 装置のコンフォーマンスステートメントからの擬態

特定の装置の DICOM の出し方（製造者・型名・ソフトウェアの版・
文字コードの組・必ず出す属性・空で出す属性・プライベートタグ・転送の
形）は、その装置のコンフォーマンスステートメント（DICOM PS3.2）を読んで
**装置のプロファイル**に写し、モダリティのテンプレートの上に重ねて
擬態する。形・写す手順・置き場は
[spec/13_device_profiles.md](13_device_profiles.md)。実在の装置の
プロファイルは公開のリポジトリに置かない（ADR-0012）。

---

## File Meta Information

### 概要

**File Meta Information**は、DICOMファイルの最初に格納される必須情報（Group 0002）。

**重要**: File Meta Informationが不完全または誤っていると、多くのDICOMビューアで読み込みエラーが発生する。

### 必須要素

| Tag | Attribute Name | Type | 値の決定方法 |
|-----|----------------|------|------------|
| (0002,0001) | File Meta Information Version | 1 | `b'\x00\x01'` (固定) |
| (0002,0002) | Media Storage SOP Class UID | 1 | テンプレートから（例: CT Image Storage） |
| (0002,0003) | Media Storage SOP Instance UID | 1 | 画像のSOP Instance UIDと同一 |
| (0002,0010) | Transfer Syntax UID | 1 | 選択されたTransfer Syntax |
| (0002,0012) | Implementation Class UID | 1 | この道具の固定の UID（`IMPLEMENTATION_CLASS_UID`。同じ実装は同じ UID。PS3.7 D.3.3.2、PS3.10 7.1） |
| (0002,0013) | Implementation Version Name | 3 | 例: "DICOM_GEN_1.1" |

### テンプレート定義例

```yaml
file_meta:
  media_storage_sop_class_uid: "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
  transfer_syntax_uid: "1.2.840.10008.1.2"  # Implicit VR Little Endian
  implementation_class_uid: "2.25.{固定UUID}"
  implementation_version_name: "DICOM_GEN_1.1"
  source_application_entity_title: ""  # オプション
```

### PyDicom実装

```python
from pydicom.dataset import FileMetaDataset, Dataset

def create_file_meta(sop_class_uid, sop_instance_uid, transfer_syntax_uid, 
                     implementation_class_uid, implementation_version_name):
    file_meta = FileMetaDataset()
    
    # 必須要素
    file_meta.FileMetaInformationVersion = b'\x00\x01'
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = transfer_syntax_uid
    file_meta.ImplementationClassUID = implementation_class_uid
    
    # オプション（推奨）
    file_meta.ImplementationVersionName = implementation_version_name
    
    return file_meta

# 使用例
ds = Dataset()
ds.file_meta = create_file_meta(
    sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
    sop_instance_uid=generated_sop_uid,
    transfer_syntax_uid="1.2.840.10008.1.2",
    implementation_class_uid="2.25.123456789...",
    implementation_version_name="DICOM_GEN_1.1"
)

# 保存時
ds.save_as("output.dcm", write_like_original=False)
```

**注意事項**:

- `write_like_original=False` を指定すること（新規ファイル作成時）
- File Metaの Transfer Syntax UID とデータセット本体の圧縮形式は一致させること

---

## UID生成スコープ

### UID種別とスコープ

| UID種別 | スコープ | 生成タイミング | 備考 |
|--------|---------|--------------|------|
| **Study Instance UID** | Study単位 | スタディ生成時に1回 | 同一スタディ内の全シリーズ・全画像で共通 |
| **Series Instance UID** | Series単位 | シリーズ生成時に1回 | 同一シリーズ内の全画像で共通 |
| **SOP Instance UID** | Instance単位 | 画像ごとに生成 | 各画像で一意 |
| **Frame of Reference UID** | Study単位 | スタディ生成時に1回 | 同一スタディ内で共通（CT/MRの場合） |
| **Instance Creator UID** | 固定 | 定数（`INSTANCE_CREATOR_UID`） | 全生成データで共通（実装者UID） |

**注意**: Frame of Reference UIDは、同一スタディ内の全シリーズで共通とする（空間座標の整合性のため）。

### UID生成方式

#### UUID 2.25方式（デフォルト）

**形式**: `2.25.{UUIDを10進数変換}`

**例**: `2.25.113059749145936325402354257176981405696`

**実装例**:

```python
import uuid

def generate_uid_uuid():
    uuid_int = uuid.uuid4().int
    return f"2.25.{uuid_int}"
```

#### カスタム Root 方式

**形式**: `{custom_root}.{生成ごとの番号}.{連番}`

- UID は世界で一意でなければならない（PS3.5 9）。連番は生成のたびに 1 に
  戻るので、生成ごとの番号（64 ビットの乱数、20 桁まで）を根の後ろに
  つなぎ、前の生成の UID と重なる見込みを無視できるほど小さくする
  （2.25 の UUID と同じく、確率による一意）
- 根は PS3.5 9.1 の形：数字と `.` だけ、2 成分以上、最初の成分は 0・1・2
  （0・1 なら 2 番目は 0〜39。ITU-T X.660）、成分の先頭に 0 を置かない
  （`0` だけの成分は可）。UID は 64 字までなので、根は 35 字まで
- 根は自分の組織に割り当てられたものを使う。他の組織の根を借りない

#### SOP Instance UIDの不正パターン生成

**要件**: 「異常」チェックボックスがONの場合、約10%の確率で0始まり不正OIDを生成

**不正パターン例**:

```text
正常: 2.25.123456789012345678901234567890
不正: 2.25.0123456.789012345678901234567890
              ^^
              0で始まるコンポーネント（DICOM規格違反）
```

**実装ロジック**:

```python
import random

def generate_uid_with_invalid(allow_invalid=False):
    uuid_int = uuid.uuid4().int
    uid = f"2.25.{uuid_int}"
    
    if allow_invalid and random.random() < 0.1:
        # 10%の確率で0始まり不正
        uid_str = str(uuid_int)
        split_pos = random.randint(3, len(uid_str) - 3)
        invalid_uid = f"2.25.0{uid_str[:split_pos]}.{uid_str[split_pos:]}"
        return invalid_uid
    
    return uid
```

---

## Pixel Data

### モード

| モード | 用途 | Bits Allocated | Pixel Representation | 表示内容 |
|--------|------|----------------|---------------------|---------|
| **simple_text** | 簡易確認 | 16 | 1 (signed) | SOP Instance UIDテキスト |
| **ct_realistic** | 医療ビューア表示 | 16 | 1 (signed) | CTリアルモード（HU値） |

### Simple Textモード

**仕様**:

- **サイズ**: 512×512ピクセル（デフォルト）
- **背景色**: 黒（8 ビットの画像の値 0 → 画素 0、HU −1024）
- **テキスト色**: 白（8 ビットの画像の値 255 → 画素 2047、HU 1023）
- **表示内容**: SOP Instance UID
- **Photometric Interpretation**: MONOCHROME2
- **Bits Allocated/Stored**: 16/12
- **High Bit**: 11
- **Pixel Representation**: 1 (signed)
- **Rescale Intercept/Slope**: −1024 / 1
- **Samples per Pixel**: 1

CT Image では Bits Allocated は 16、Bits Stored は 12〜16、Rescale
Intercept・Slope は Type 1（PS3.3 C.8.2.1.1.4・C.8.2.1.1.5）。文字は
Pillow で 8 ビットの画像に描き、`DICOMBuilder` が 0〜255 を 0〜2047 に
広げて CT の画素として書く。

### CT Realisticモード（医療ビューア対応）

**仕様**:

- **サイズ**: 512×512ピクセル（デフォルト）
- **Photometric Interpretation**: MONOCHROME2
- **Bits Allocated**: 16
- **Bits Stored**: 12-16（Job の `pixel_spec.bits_stored`。12 未満は誤り。
  PS3.3 C.8.2.1.1.5）
- **High Bit**: 11-15
- **Pixel Representation**: 1 (signed, 2's complement)
- **Samples per Pixel**: 1
- **Rescale Intercept**: -1024（HU値変換用）
- **Rescale Slope**: 1
- **Window Center**: [40, 400]（例: Soft Tissue, Lung）
- **Window Width**: [400, 1500]

**ピクセル値とHU値の関係**:

```text
HU = Pixel Value × Rescale Slope + Rescale Intercept
```

**例**:

- Pixel Value = 0 → HU = 0 × 1 + (-1024) = -1024 (Air)
- Pixel Value = 1024 → HU = 1024 × 1 + (-1024) = 0 (Water)
- Pixel Value = 2024 → HU = 2024 × 1 + (-1024) = 1000 (Bone)

**画素の値の範囲**（PS3.3 C.7.6.3 の Pixel Representation、PS3.5 8）:

Pixel Representation 1 の画素は、Bits Stored のビット数の 2 の補数で
表す。値は −2^(Bits Stored − 1) 〜 2^(Bits Stored − 1) − 1 に収める。
12 ビットなら −2048〜2047 で、この道具は 0〜2047（HU −1024〜1023）を
使う。範囲を超える値は、読む側が High Bit で符号を広げるため別の値に
化ける（12 ビットの 2048 は −2048）。`DICOMBuilder` は範囲を超える
画素を `DICOMBuildError` で止める。

**生成パターン**:

1. **gradient**: 左から右へHU値が増加（12 ビットで HU −1024〜1023）
2. **circle**: 中心に高HU値の円（ボーン、HU 1000）、周辺に低HU値
   （ソフトティッシュ、HU 40）。Bits Stored の上限を超えるときは上限に収める
3. **noise**: 0 から Bits Stored の上限までの一様な乱数

**対応するDICOMタグ**:

| Tag | Attribute Name | Value (CT Realistic) |
|-----|----------------|----------------------|
| (0028,0002) | Samples per Pixel | 1 |
| (0028,0004) | Photometric Interpretation | "MONOCHROME2" |
| (0028,0010) | Rows | 512 |
| (0028,0011) | Columns | 512 |
| (0028,0100) | Bits Allocated | 16 |
| (0028,0101) | Bits Stored | 12〜16（既定 12） |
| (0028,0102) | High Bit | Bits Stored − 1 |
| (0028,0103) | Pixel Representation | 1 |
| (0028,1052) | Rescale Intercept | -1024 |
| (0028,1053) | Rescale Slope | 1 |
| (0028,1050) | Window Center | [40, 400] |
| (0028,1051) | Window Width | [400, 1500] |

---

## CT Image の必須の属性

CT Image IOD（PS3.3 A.3）の Type 1・2・2C の属性のうち、Job・テンプレート・
予約から値が来ないものは、`DICOMBuilder` が次の既定値で必ず出す。
装置のプロファイルの `attributes.set` で変えられ、`omit` では消せない。
Type 1 の Image Type は `empty` と空の `set` でも空にできない
（spec/13 の 3.3）。

| Tag | Attribute Name | Module | Type | 既定値 | 規格の節 |
|-----|----------------|--------|------|--------|----------|
| (0008,0008) | Image Type | CT Image | 1 | `ORIGINAL\PRIMARY\AXIAL` | PS3.3 C.8.2.1.1.1 |
| (0018,5100) | Patient Position | General Series | 2C（CT Image Storage では必須） | `HFS` | PS3.3 C.7.3.1、C.7.3.1.1.2 |
| (0020,1040) | Position Reference Indicator | Frame of Reference | 2 | 空 | PS3.3 C.7.4.1、C.7.4.1.1.2 |

CT の Image Type の値 3 の Defined Terms は `AXIAL` と `LOCALIZER`
（C.8.2.1.1.1。`AXIAL` は断層の画像を指し、横断に限らない）。この道具は
断層の画像を作るので、既定を `AXIAL` にする。

---

## マルチスライス空間座標

### 関連タグ

| Tag | Attribute Name | Type | 連動ルール |
|-----|----------------|------|----------|
| (0020,0013) | Instance Number | 2 | 1からの連番 |
| (0020,0032) | Image Position (Patient) | 1 | [X, Y, Z] - Zを変化させる |
| (0020,1041) | Slice Location | 3 | Zと同一値またはZ基準の連番 |
| (0018,0050) | Slice Thickness | 2 | 全画像で共通 |
| (0028,0030) | Pixel Spacing | 1 | [行間隔, 列間隔] - 全画像で共通 |

### 空間座標計算ロジック

**計算式**:

```python
def calculate_spatial_coords(slice_index, slice_thickness, slice_spacing, start_z):
    """スライスインデックス（0始まり）から空間座標を計算"""
    instance_number = slice_index + 1  # 1始まり
    
    # Z座標
    z = start_z + (slice_index * slice_spacing)
    
    # Image Position (Patient)
    # X, Yは固定、Zのみ変化
    image_position = [0.0, 0.0, z]
    
    # Slice Location
    slice_location = z
    
    return {
        "instance_number": instance_number,
        "image_position_patient": image_position,
        "slice_location": slice_location
    }
```

**例**: 20枚のスライス、厚さ5mm、間隔5mm、開始Z=0

| Slice Index | Instance Number | Image Position (Patient) | Slice Location |
|-------------|----------------|-------------------------|----------------|
| 0 | 1 | [0, 0, 0] | 0 |
| 1 | 2 | [0, 0, 5] | 5 |
| 2 | 3 | [0, 0, 10] | 10 |
| ... | ... | ... | ... |
| 19 | 20 | [0, 0, 95] | 95 |

### DS の書き方

DS（Decimal String）は 16 バイトまで（PS3.5 6.2 の表 6.2-1）。
`str(float)` は浮動小数の誤差で 16 字を超える（間隔 0.1 の 4 枚目は
`0.30000000000000004`、身長 165.7 cm は `1.6569999999999998` m）。
この道具が数から作る DS（Image Position (Patient)・Image Orientation
(Patient)・Slice Location・Slice Thickness・Pixel Spacing・Patient's
Weight・Patient's Size）は、有効 12 桁で丸めてから
`pydicom.valuerep.format_number_as_ds` で 16 字以内にする
（`app/core/generator.py` の `format_ds`）。上の例は `0.3`・`1.657` になる。
小さい値は 0 にせず、指数の形で残す（`1e-07`。DS は指数の形を許す）。

### テンプレート設定

```yaml
spatial:
  slice_thickness: 5.0      # mm
  slice_spacing: 5.0        # mm（通常はthicknessと同じ）
  start_z: 0.0              # mm
  pixel_spacing: [0.5, 0.5] # [行, 列] mm
  image_orientation_patient: [1, 0, 0, 0, 1, 0]  # 標準軸位断
```

---

## 文字コード（多言語）

### Specific Character Set (0008,0005)

| 値 | エンコーディング | 用途 | PN対応 |
|----|----------------|------|--------|
| （空文字） | ASCII | 英数字のみ | alphabeticのみ |
| `ISO_IR 100` | ISO 8859-1 (Latin-1) | 西欧言語 | alphabeticのみ |
| `ISO 2022 IR 87` | ISO-2022-JP | 日本語（JIS） | alphabetic + ideographic + phonetic |
| `ISO_IR 192` | UTF-8 | 多言語 | alphabetic + ideographic + phonetic |

### PN (Person Name) の構造

**形式**: `{Alphabetic}={Ideographic}={Phonetic}`

**例**:

```text
YAMADA^TARO=山田^太郎=ヤマダ^タロウ
```

各コンポーネント:

- **Alphabetic**: ローマ字（ASCII）
- **Ideographic**: 漢字（ISO 2022 IR 87またはUTF-8）
- **Phonetic**: カタカナ（ISO 2022 IR 87またはUTF-8）

### 病院テンプレートでの制御

#### A病院（日本語使用）

```yaml
overrides:
  character_set:
    default: "ISO 2022 IR 6\\ISO 2022 IR 87"
  
  patient_module:
    patient_name:
      use_alphabetic: true
      use_ideographic: true
      use_phonetic: true
```

**期待する出力**:

```text
(0008,0005) Specific Character Set: "ISO 2022 IR 6\ISO 2022 IR 87"
(0010,0010) Patient's Name: "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"
```

#### B病院（ローマ字のみ）

```yaml
overrides:
  character_set:
    default: ""  # ASCII
  
  patient_module:
    patient_name:
      use_alphabetic: true
      use_ideographic: false
      use_phonetic: false
```

**期待する出力**:

```text
(0008,0005) Specific Character Set: (空)
(0010,0010) Patient's Name: "YAMADA^TARO"
```

### PyDicom実装注意点

```python
from pydicom.dataset import Dataset

# 日本語使用の場合
ds = Dataset()
ds.SpecificCharacterSet = ['ISO 2022 IR 6', 'ISO 2022 IR 87']
ds.PatientName = "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"

# PyDicomはデフォルトと拡張文字集合を使い分けてエンコード
ds.save_as("output.dcm")

# ローマ字のみの場合
ds2 = Dataset()
ds2.SpecificCharacterSet = ''  # または設定しない
ds2.PatientName = "YAMADA^TARO"
ds2.save_as("output2.dcm")
```

## PatientAge (0010,1010)

`PatientAge` は Job YAML の `patient.age` をそのまま使用せず、
`birth_date` と `study_date` から **日本法基準** で算出する。

### 法的根拠

- **年齢計算ニ関スル法律**（明治35年法律第50号）: 出生の日より起算
- **民法143条**: 期間を年で定めた場合、暦に従い計算。応当日がない場合はその月の末日に満了

### アルゴリズム

加齢日（N歳に達する日）= 誕生日の前日のN年後。

```python
from datetime import date, timedelta

def _age_reached_date(birth: date, n: int) -> date:
    """N歳到達日（加齢日）を算出"""
    eve = birth - timedelta(days=1)  # 誕生日の前日
    target_year = eve.year + n
    try:
        return eve.replace(year=target_year)
    except ValueError:
        # eve=2/29（birth=3/1、閏年）で非閏年の場合 → 2/28
        return date(target_year, eve.month, 28)
```

### 具体例（2/29生まれ）

| 生年月日 | 検査日 | 期待値 | 理由 |
|---------|--------|-------|------|
| 2000-02-29 | 2025-02-27 | 024Y | 加齢日(2/28)の前日 |
| 2000-02-29 | 2025-02-28 | 025Y | 非閏年の加齢日 |
| 2000-02-29 | 2024-02-28 | 024Y | 閏年の加齢日 |

### 制約

- `study_date >= birth_date` を必須とする（バリデーションエラー）
- DICOM AS 形式: `nnnY`（0〜999の範囲、範囲外はビルドエラー）

---

## Transfer Syntax

### サポートするTransfer Syntax

| Transfer Syntax | UID | VR | Endian |
|----------------|-----|-----|--------|
| **Implicit VR Little Endian** | 1.2.840.10008.1.2 | Implicit | Little |
| **Explicit VR Little Endian** | 1.2.840.10008.1.2.1 | Explicit | Little |

この 2 つが `app/core/generator.py` の `DICOMBuilder` が受ける転送構文で、
ほかの UID は `DICOMBuildError` になる。

Explicit VR Big Endian（1.2.840.10008.1.2.2）は規格で廃止された形
（PS3.5 A.3）なので作らない。前は受けていたが、画素（OW）を Little
Endian のバイト列のまま書いていて、読み戻すと値が入れ替わった
（PS3.5 8）。Job や装置のプロファイルで指定すると、出力のフォルダを
作る前に `DICOMValidationError`（CLI の終了コード 4）で止める。装置の
プロファイルの最初の転送の形が Big Endian なら `ProfileMismatchError`。
異常のデータの約束（spec/02）にも無いので、異常のデータのレベルに関わらず
作らない（上の「ふつうの経路と異常のデータの経路」）。

### PyDicom実装

```python
from pydicom.dataset import Dataset, FileMetaDataset

def save_with_transfer_syntax(ds, filepath, transfer_syntax_uid):
    # File Metaに設定
    ds.file_meta.TransferSyntaxUID = transfer_syntax_uid
    
    # Implicit VRの場合
    if transfer_syntax_uid == "1.2.840.10008.1.2":
        ds.is_implicit_VR = True
        ds.is_little_endian = True
    
    # Explicit VR Little Endianの場合
    elif transfer_syntax_uid == "1.2.840.10008.1.2.1":
        ds.is_implicit_VR = False
        ds.is_little_endian = True
    
    ds.save_as(filepath, write_like_original=False)
```

---

## DICOMタグ Type定義

| Type | 説明 | 要件 |
|------|------|------|
| 1 | Required | 必須、空値不可 |
| 1C | Conditional | 条件付き必須 |
| 2 | Required, Empty if Unknown | 必須、値不明時は空値可 |
| 2C | Conditional | 条件付き必須、値不明時は空値可 |
| 3 | Optional | オプション |

---

## VR (Value Representation) 一覧

| VR | 名称 | 説明 | 例 |
|----|------|------|-----|
| AE | Application Entity | AEタイトル | "PACS" |
| AS | Age String | 年齢 | "040Y" |
| CS | Code String | コード文字列 | "M" |
| DA | Date | 日付 | "20240115" |
| DS | Decimal String | 10進数文字列（16バイト） | "12.5" |
| IS | Integer String | 整数文字列 | "100" |
| LO | Long String | 長い文字列（64文字） | "CT CHEST" |
| LT | Long Text | 長いテキスト（10240文字） | コメント等 |
| PN | Person Name | 人名 | "YAMADA^TARO" |
| SH | Short String | 短い文字列（16文字） | "ACC001" |
| TM | Time | 時刻 | "143000" |
| UI | Unique Identifier | UID | "2.25.123..." |
| US | Unsigned Short | 符号なし16bit整数 | 512 |

---

## 参考資料

1. **DICOM Standard**: <https://www.dicomstandard.org/>
2. **PyDicom Documentation**: <https://pydicom.github.io/>
3. **IHE Japan**: <https://www.ihe-j.org/> (OID取得情報)
4. **RFC 3061**: UUID Based OID (2.25系)
5. **装置のコンフォーマンスステートメント**（DICOM PS3.2 Annex N の形）：
   擬態する装置ごとに読む。どの文書のどの版を写したかは、外の置き場の
   プロファイルの `source` に書く（spec/13）
