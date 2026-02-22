# 06. DICOM医療仕様

## 概要

このドキュメントでは、医療DICOMの詳細仕様を定義する。

**重要**: この仕様は医療標準に準拠しており、変更不可。

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
| (0002,0012) | Implementation Class UID | 1 | 実装者のUID（2.25または組織OID） |
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
| **Instance Creator UID** | 固定 | アプリ起動時に1回 | 全生成データで共通（実装者UID） |

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
| **simple_text** | 簡易確認 | 8 | 0 (unsigned) | SOP Instance UIDテキスト |
| **ct_realistic** | 医療ビューア表示 | 16 | 1 (signed) | CTリアルモード（HU値） |

### Simple Textモード

**仕様**:
- **サイズ**: 512×512ピクセル（デフォルト）
- **背景色**: 黒（値=0）
- **テキスト色**: 白（値=255）
- **表示内容**: SOP Instance UID
- **Photometric Interpretation**: MONOCHROME2
- **Bits Allocated/Stored**: 8/8
- **High Bit**: 7
- **Pixel Representation**: 0 (unsigned)
- **Samples per Pixel**: 1

### CT Realisticモード（医療ビューア対応）

**仕様**:
- **サイズ**: 512×512ピクセル（デフォルト）
- **Photometric Interpretation**: MONOCHROME2
- **Bits Allocated**: 16
- **Bits Stored**: 12-16（テンプレート設定による）
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
- Pixel Value = 2048 → HU = 2048 × 1 + (-1024) = 1024 (Bone)

**生成パターン**:

1. **gradient**: 左から右へHU値が増加
2. **circle**: 中心に高HU値の円（ボーン）、周辺に低HU値（ソフトティッシュ）
3. **noise**: ランダムノイズを加えてリアル感を演出

**対応するDICOMタグ**:

| Tag | Attribute Name | Value (CT Realistic) |
|-----|----------------|----------------------|
| (0028,0002) | Samples per Pixel | 1 |
| (0028,0004) | Photometric Interpretation | "MONOCHROME2" |
| (0028,0010) | Rows | 512 |
| (0028,0011) | Columns | 512 |
| (0028,0100) | Bits Allocated | 16 |
| (0028,0101) | Bits Stored | 12 or 16 |
| (0028,0102) | High Bit | 11 or 15 |
| (0028,0103) | Pixel Representation | 1 |
| (0028,1052) | Rescale Intercept | -1024 |
| (0028,1053) | Rescale Slope | 1 |
| (0028,1050) | Window Center | [40, 400] |
| (0028,1051) | Window Width | [400, 1500] |

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
    default: "ISO 2022 IR 87"
  
  patient_module:
    patient_name:
      use_alphabetic: true
      use_ideographic: true
      use_phonetic: true
```

**期待する出力**:

```text
(0008,0005) Specific Character Set: "ISO 2022 IR 87"
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
ds.SpecificCharacterSet = 'ISO 2022 IR 87'
ds.PatientName = "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"

# PyDicomは自動的にISO 2022 IR 87でエンコード
ds.save_as("output.dcm")

# ローマ字のみの場合
ds2 = Dataset()
ds2.SpecificCharacterSet = ''  # または設定しない
ds2.PatientName = "YAMADA^TARO"
ds2.save_as("output2.dcm")
```

---

## Transfer Syntax

### サポートするTransfer Syntax

| Transfer Syntax | UID | VR | Endian | Phase |
|----------------|-----|-----|--------|-------|
| **Implicit VR Little Endian** | 1.2.840.10008.1.2 | Implicit | Little | Phase 1 |
| **Explicit VR Little Endian** | 1.2.840.10008.1.2.1 | Explicit | Little | Phase 1 |
| Explicit VR Big Endian | 1.2.840.10008.1.2.2 | Explicit | Big | Phase 2 |

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
| DS | Decimal String | 10進数文字列 | "12.5" |
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

1. **DICOM Standard**: https://www.dicomstandard.org/
2. **PyDicom Documentation**: https://pydicom.github.io/
3. **FUJIFILM SCENARIA View Conformance Statement**: SCENARIA-View_DICOM-Conformance-Statement_rev01_20221025.pdf
4. **IHE Japan**: https://www.ihe-j.org/ (OID取得情報)
5. **RFC 3061**: UUID Based OID (2.25系)
