# 02. Core Engine

## 概要

**Core Engine** はDICOM生成の中核ロジックを提供する。UI非依存で、単体テスト可能。

**重要設計原則**:

- Pure Python（外部UI依存なし）
- 関数型スタイル（状態を持たない）
- 明確な入出力

---

## API一覧

### 主要クラス

| クラス名 | 責務 | モジュール |
|---------|------|-----------|
| `UIDGenerator` | UID生成 | `uid_generator.py` |
| `PixelGenerator` | ピクセルデータ生成 | `pixel_generator.py` |
| `FileMetaBuilder` | File Meta Information構築 | `dicom_writer.py` |
| `SpatialCalculator` | 空間座標計算 | `dicom_writer.py` |
| `DICOMBuilder` | DICOM Dataset構築 | `generator.py` |
| `AbnormalGenerator` | 異常データ生成 | `abnormal_generator.py` |

以降の節は、これらのクラスの仕様を書く。クラスの外にある Core のモジュールは
「Core のそのほかのモジュール」にまとめる。

**`AbnormalGenerator` の接続**: `StudyGeneratorService.generate` は、
`abnormal.level` で生成した `AbnormalGenerator` を、Dataset を組み立てた後
（テンプレート・予約・装置プロファイルを適用した後）に、画像1枚ごとに適用する。
`generate` を経由する経路（`generate`・`quick`・モダリティエミュレーターの撮影・
GUI）はすべてこの処理を経由する。`level` が `none`（既定）のときは何も変えない。
`abnormal.allow_invalid_sop_uid`（SOP Instance UID の 0 始まり）は `level` とは
別の設定で、`level` に関わらず有効。
レベルの指定は、Job YAML の `abnormal.level`、`generate` / `quick` の
`--abnormal-level`（`generate` では CLI が Job YAML より優先）、
モダリティエミュレーターの `exam --abnormal-level` と画面の「異常のデータ」。

---

## UIDGenerator

### 目的

DICOM UID（Study, Series, SOP Instance等）を生成する。

### インターフェース

```python
class UIDGenerator:
    """UID生成器
    
    2つの生成方式をサポート：
    1. UUID 2.25方式（デフォルト）
    2. カスタムRoot方式（組織OID取得済みの場合）
    """
    
    def __init__(
        self,
        method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25",
        custom_root: str = "",
        run_scoped: bool = False,
    ):
        """
        Args:
            method: UID生成方式
            custom_root: カスタムRoot使用時のOID（自分の組織に割り当てられた根。
                例の "1.2.3.4.5" は架空）
            run_scoped: True なら根の後ろに生成ごとの番号（64 ビットの乱数）を
                つなぐ。`StudyGeneratorService` は True で使う
        """
        pass
    
    def generate_study_uid(self) -> str:
        """Study Instance UIDを生成
        
        スコープ: Study単位（1スタディにつき1回）
        
        Returns:
            str: 例 "2.25.123456789012345678901234567890"
        """
        pass
    
    def generate_series_uid(self) -> str:
        """Series Instance UIDを生成
        
        スコープ: Series単位（1シリーズにつき1回）
        """
        pass
    
    def generate_sop_uid(self, allow_invalid: bool = False) -> str:
        """SOP Instance UIDを生成
        
        スコープ: Instance単位（各画像ごと）
        
        Args:
            allow_invalid: Trueの場合、10%の確率で0始まり不正OIDを生成
        
        Returns:
            str: 正常または不正（0始まり）UID
        """
        pass
    
    def generate_frame_of_reference_uid(self) -> str:
        """Frame of Reference UIDを生成
        
        スコープ: Study単位（同一スタディ内で共通）
        """
        pass
    
    def generate_instance_creator_uid(self) -> str:
        """Instance Creator UIDを生成
        
        生成の側（`StudyGeneratorService`）は使わない。Instance Creator UID と
        Implementation Class UID は、`app/services/study_generator.py` の
        定数（`INSTANCE_CREATOR_UID`・`IMPLEMENTATION_CLASS_UID`）で、
        すべての生成で同じ値を使う（PS3.7 D.3.3.2、PS3.10 7.1。spec/06）
        """
        pass
```

### 使用例

```python
# UUID 2.25方式（デフォルト）
uid_gen = UIDGenerator(method="uuid_2_25")
study_uid = uid_gen.generate_study_uid()
# => "2.25.113059749145936325402354257176981405696"

# カスタムRoot方式（根は架空の例）
uid_gen = UIDGenerator(
    method="custom_root",
    custom_root="1.2.3.4.5",
    run_scoped=True,
)
study_uid = uid_gen.generate_study_uid()
# => "1.2.3.4.5.{生成ごとの番号}.1"
```

### 実装詳細

- **UUID 2.25**: `uuid.uuid4().int` を10進数変換
- **カスタムRoot**: `{root}.{counter}` で連番管理。`run_scoped=True` なら
  `{root}.{run_id}.{counter}`。`run_id` は生成器ごとの 64 ビットの乱数で、
  連番が生成のたびに 1 に戻っても、前の生成の UID と重複する確率は
  無視できる（UID は世界で一意。PS3.5 9。一意性は 2.25 と同じく確率による）
- **ルートの形式**（PS3.5 9.1）：数字と `.` だけ、2 成分以上、最初の成分は
  0・1・2（0・1 なら 2 番目は 0〜39）、成分の先頭に 0 を置かない（`0` だけの
  成分は可）、64 文字まで。`run_scoped=True` なら、番号と連番を連結しても
  64 文字に収まるよう、ルートは `CUSTOM_ROOT_MAX_LENGTH`（35 文字）まで
- 生成した UID が 64 文字を超えるときは `UIDGenerationError`
- **0始まり不正**: ランダムな位置でドットの直後に0を置く
- 方式が不正、`custom_root` が空または OID の形式でないときは
  `UIDGenerationError`

---

## PixelGenerator

### 目的

ピクセルデータ（numpy配列）を生成する。

### インターフェース

```python
class PixelGenerator:
    """ピクセルデータ生成器
    
    2つのモードをサポート：
    1. Simple Text: SOP Instance UID表示（8bit）
    2. CT Realistic: 医療ビューア対応（16bit signed）
    """
    
    def generate_simple_text(
        self,
        sop_instance_uid: str,
        width: int = 512,
        height: int = 512
    ) -> np.ndarray:
        """Simple Textモードのピクセルデータ生成
        
        Args:
            sop_instance_uid: 表示するUID
            width: 画像幅（ピクセル）
            height: 画像高さ（ピクセル）
        
        Returns:
            np.ndarray: shape=(height, width), dtype=uint8
        """
        pass
    
    def generate_ct_realistic(
        self,
        width: int = 512,
        height: int = 512,
        pattern: Literal["gradient", "circle", "noise"] = "gradient",
        bits_stored: int = 12
    ) -> np.ndarray:
        """CT Realisticモードのピクセルデータ生成
        
        Args:
            width: 画像幅
            height: 画像高さ
            pattern: パターン種類
            bits_stored: Bits Stored（12〜16。PS3.3 C.8.2.1.1.5）
        
        Returns:
            np.ndarray: shape=(height, width), dtype=int16
        """
        pass
```

### 使用例

```python
pixel_gen = PixelGenerator()

# Simple Text
pixels_text = pixel_gen.generate_simple_text(
    sop_instance_uid="2.25.123..."
)
# => shape=(512, 512), dtype=uint8, 黒背景に白文字

# CT Realistic
pixels_ct = pixel_gen.generate_ct_realistic(
    pattern="gradient",
    bits_stored=12
)
# => shape=(512, 512), dtype=int16, HU値対応
```

### CTリアルモードの詳細

**パターン**:

- `gradient`: 左→右で HU値 -1024 → Bits Stored の上限（12 ビットで 1023）
- `circle`: 中心に高HU値の円（Bone）、周辺は低HU値（Soft Tissue）
- `noise`: ランダムノイズ

値は Bits Stored の符号ありの範囲に収める（spec/06 の「画素の値の範囲」。
PS3.5 8）。

**HU値変換**:

```text
HU = Pixel Value × Rescale Slope + Rescale Intercept
Rescale Intercept = -1024
Rescale Slope = 1
```

---

## FileMetaBuilder

### 目的

File Meta Information (Group 0002) を構築する。

### インターフェース

```python
class FileMetaBuilder:
    """File Meta Information構築器"""
    
    def build(
        self,
        sop_class_uid: str,
        sop_instance_uid: str,
        transfer_syntax_uid: str,
        implementation_class_uid: str,
        implementation_version_name: str
    ) -> FileMetaDataset:
        """File Metaを構築
        
        Args:
            sop_class_uid: Media Storage SOP Class UID
            sop_instance_uid: Media Storage SOP Instance UID
            transfer_syntax_uid: Transfer Syntax UID
            implementation_class_uid: 実装者UID
            implementation_version_name: 実装バージョン名
        
        Returns:
            FileMetaDataset: PyDicomのFile Meta
        """
        pass
```

### 使用例

```python
from pydicom.dataset import FileMetaDataset

builder = FileMetaBuilder()
file_meta = builder.build(
    sop_class_uid="1.2.840.10008.5.1.4.1.1.2",  # CT Image Storage
    sop_instance_uid=sop_uid,
    transfer_syntax_uid="1.2.840.10008.1.2",    # Implicit VR Little Endian
    implementation_class_uid="2.25.123...",
    implementation_version_name="DICOM_GEN_1.1"
)
```

### 必須要素

| Tag | Attribute Name | Value |
|-----|----------------|-------|
| (0002,0001) | File Meta Information Version | `b'\x00\x01'` |
| (0002,0002) | Media Storage SOP Class UID | 引数から |
| (0002,0003) | Media Storage SOP Instance UID | 引数から |
| (0002,0010) | Transfer Syntax UID | 引数から |
| (0002,0012) | Implementation Class UID | 引数から |
| (0002,0013) | Implementation Version Name | 引数から |

---

## SpatialCalculator

### 目的

マルチスライス時の空間座標を計算する。

### インターフェース

```python
@dataclass
class SpatialCoordinates:
    """空間座標データ"""
    instance_number: int
    image_position_patient: list[float]  # [X, Y, Z]
    slice_location: float

class SpatialCalculator:
    """空間座標計算器"""
    
    def __init__(
        self,
        slice_thickness: float,
        slice_spacing: float,
        start_z: float = 0.0
    ):
        """
        Args:
            slice_thickness: スライス厚（mm）
            slice_spacing: スライス間隔（mm）
            start_z: 開始Z座標（mm）
        """
        pass
    
    def calculate(self, slice_index: int) -> SpatialCoordinates:
        """指定スライスインデックスの空間座標を計算
        
        Args:
            slice_index: スライスインデックス（0始まり）
        
        Returns:
            SpatialCoordinates: 計算結果
        """
        pass
```

### 使用例

```python
calc = SpatialCalculator(
    slice_thickness=5.0,
    slice_spacing=5.0,
    start_z=0.0
)

for i in range(20):
    coords = calc.calculate(i)
    print(f"Slice {i}: Instance#{coords.instance_number}, Z={coords.slice_location}")

# Slice 0: Instance#1, Z=0.0
# Slice 1: Instance#2, Z=5.0
# Slice 2: Instance#3, Z=10.0
# ...
```

### 計算式

```text
instance_number = slice_index + 1  # 1始まり
z = start_z + (slice_index * slice_spacing)
image_position_patient = [0.0, 0.0, z]
slice_location = z
```

---

## DICOMBuilder

### 目的

各種データを統合してDICOM Datasetを構築する。

### インターフェース

```python
class DICOMBuilder:
    """DICOM Dataset構築器（メインクラス）"""
    
    def build_ct_image(
        self,
        patient: Patient,
        study_config: StudyConfig,
        series_config: SeriesConfig,
        instance_config: InstanceConfig,
        uid_context: UIDContext,
        spatial: SpatialCoordinates,
        pixel_data: np.ndarray,
        file_meta: FileMetaDataset,
        sop_instance_uid: str,
        series_instance_uid: str,
        specific_character_set: str | None = None,
        use_ideographic: bool = True,
        use_phonetic: bool = True,
        bits_stored: int = 16
    ) -> Dataset:
        """CT Image Storageを構築
        
        Args:
            patient: 患者情報
            study_config: スタディ設定
            series_config: シリーズ設定
            instance_config: インスタンス設定
            uid_context: UID情報
            spatial: 空間座標
            pixel_data: ピクセルデータ
            file_meta: File Meta Information
                （Media Storage SOP Instance UID が sop_instance_uid と
                異なれば DICOMBuildError）
            sop_instance_uid: SOP Instance UID
            series_instance_uid: Series Instance UID
            specific_character_set: Specific Character Set（None なら設定しない）
            use_ideographic: PN に漢字表記を入れるか
            use_phonetic: PN にカナ表記を入れるか
            bits_stored: Bits Stored
        
        Returns:
            Dataset: 完成したDICOM Dataset
        """
        pass
```

`DICOMBuilder` は患者・スタディ・シリーズ・画像・空間座標・ピクセルの各タグを
設定するだけで、テンプレートの属性・予約の値・装置プロファイルは重ねない。
重ねる順序は `StudyGeneratorService` が持つ（[architecture.md](../architecture.md)
の「生成の流れ」）。異常値の注入も `DICOMBuilder` は行わない。

### 使用例

```python
builder = DICOMBuilder()

ds = builder.build_ct_image(
    patient=patient,
    study_config=study_config,
    series_config=series_config,
    instance_config=instance_config,
    uid_context=uid_ctx,
    spatial=spatial_coords,
    pixel_data=pixels,
    file_meta=file_meta,
    sop_instance_uid=sop_uid,
    series_instance_uid=series_uid,
)

# 保存
ds.save_as("output.dcm", write_like_original=False)
```

### 内部処理フロー

1. File Meta を Dataset に設定
2. Patient Module タグ設定（Patient's Age は生年月日と検査日から算出）
3. General Study Module タグ設定（Referring Physician's Name は Type 2 なので、
   Job に無ければ空の値で出力する。PS3.3 C.7.2.1）
4. General Series Module タグ設定（Patient Position の既定値 `HFS` を含む）
5. Frame of Reference Module タグ設定（Position Reference Indicator は空）
6. General Image Module・CT Image Module タグ設定（Image Type の既定値
   `ORIGINAL\PRIMARY\AXIAL` を含む。spec/06 の「CT Image の必須の属性」）
7. SOP Common Module タグ設定
8. 空間座標タグ設定（DS は 16 文字以内。spec/06 の「DS の書き方」）
9. Pixel Data設定（画素が Bits Stored の範囲に収まるかを検証する）
10. Transfer Syntax に合わせた設定
11. Dataset返却

---

## AbnormalGenerator

### 目的

異常データ（不正値）を生成する。

### インターフェース

```python
class AbnormalGenerator:
    """異常データ生成器"""
    
    def __init__(self, level: Literal["none", "mild", "moderate", "severe"]):
        """
        Args:
            level: 異常レベル
                - none: 正常データ
                - mild: VR違反、文字数超過
                - moderate: 必須タグ欠落、UID不正
                - severe: File Meta破損、Pixel Data欠落
        """
        pass
    
    def apply_abnormal_value(
        self,
        tag_name: str,
        normal_value: Any,
        vr: str,
        tag_type: int,
        max_length: Optional[int] = None
    ) -> Optional[Any]:
        """異常値を適用
        
        Args:
            tag_name: タグ名（例: "PatientID"）
            normal_value: 正常値
            vr: Value Representation
            tag_type: DICOM Type (1, 2, 3等)
            max_length: 最大長（VRによる）
        
        Returns:
            異常値 or None（タグ欠落の場合）
        """
        pass
```

### 使用例

```python
abnormal_gen = AbnormalGenerator(level="mild")

# Patient ID に異常値適用
patient_id = abnormal_gen.apply_abnormal_value(
    tag_name="PatientID",
    normal_value="P000001",
    vr="LO",
    tag_type=2,
    max_length=16
)
# => "INVALID_ID_STRING_OVER_16_CHARS"  (文字数超過)
```

### レベル別挙動

| Level | 挙動 |
|-------|------|
| **none** | 正常値をそのまま返す |
| **mild** | VR違反、文字数超過 |
| **moderate** | Type 1,2タグをNone返却（欠落）、UID 0始まり |
| **severe** | File Meta破損、Pixel Data欠落 |

### Dataset への適用

`apply_abnormal_to_dataset(dataset, generator)`（`abnormal_generator.py`）が、
次の表のタグのうち Dataset にあるものに `apply_abnormal_value` を適用する。
表に無いタグは壊さない。壊した値が `None` ならタグを削除する。

| タグ | VR | Type | 最大長 |
|------|----|------|--------|
| PatientName | PN | 2 | — |
| PatientID | LO | 2 | 64 |
| PatientBirthDate | DA | 2 | — |
| PatientSex | CS | 2 | — |
| StudyInstanceUID | UI | 1 | — |
| StudyDate | DA | 2 | — |
| StudyTime | TM | 2 | — |
| AccessionNumber | SH | 2 | 16 |
| Modality | CS | 1 | — |
| SeriesInstanceUID | UI | 1 | — |
| SeriesNumber | IS | 2 | — |
| InstanceNumber | IS | 1 | — |
| SOPClassUID | UI | 1 | — |
| SOPInstanceUID | UI | 1 | — |

- `severe` は、この表の処理に加えて Pixel Data を削除する。
- **File Meta の破損は、現在は実装していない。** File Meta の値は壊さず、
  Dataset 側の SOP Instance UID だけが File Meta と食い違うことがある。
- IS・DS の不正な文字列は、pydicom の検証を通過しないので、生の値として入れる。
- Study Instance UID を削除した画像でも撮影の結果を返せるよう、画像から Study UID
  を読み取る処理は、タグが無ければ空にする。
- 壊し方の一部は乱数で決まる（`random`）。同じレベルでも画像ごとに値が異なる。
- **定義の範囲**：異常のデータで生成する規格の違反は、上の表のタグの壊し方・
  Pixel Data の削除・`allow_invalid_sop_uid` の SOP Instance UID の 0 始まり
  だけ。Transfer Syntax・画素値・File Meta は定義に含まれない（廃止された
  Explicit VR Big Endian は異常のデータでも生成しない）。通常の経路の規格の
  チェックは、この定義の壊し方を妨げない（spec/06 の「通常の経路と異常のデータの
  経路」、[ADR-0014](../decisions/0014-separate-normal-and-abnormal-paths.md)）

---

## Core のそのほかのモジュール

モダリティエミュレーター（[12_modality_emulator.md](12_modality_emulator.md)）と
装置プロファイル（[13_device_profiles.md](13_device_profiles.md)）のために、Core に
Pure な処理が追加された。どれも通信・ファイル・ログを使わない。ここでは役割だけを
書き、詳細は各仕様を正本とする。

| モジュール | 役割 | 仕様 |
|-----------|------|------|
| `models.py` | データモデル（Pydantic）。予約の値の `WorklistItem`・`ScheduledPatient`・`ScheduledContext` を含む | [03](03_data_models.md) |
| `exceptions.py` | 例外の階層。`ModalityError`・`ProfileError` の系統を含む | [08](08_error_handling.md) |
| `device_profile.py` | 装置プロファイルのモデルと、Dataset への重ね方（`DeviceProfile`、`apply_device_profile`） | [13](13_device_profiles.md) |
| `worklist_mapping.py` | ワークリストの応答から `WorklistItem` を作成し、予約（または予約なし）の値を画像へ転記する。予約のキーの計算、モダリティの一致の検証を含む | [12](12_modality_emulator.md) の 5〜6 章 |
| `worklist_charset.py` | 画像の Specific Character Set の決定と、その文字コードで表現できない文字の検証 | [12](12_modality_emulator.md) の 7 章 |
| `path_safety.py` | 信用できない値から、ファイル・フォルダの名前を安全に作る。出力フォルダの外に書き出さないことの検証 | [12](12_modality_emulator.md) の 6 章 |
| `uid_format.py` | 相手から来る UID の形式の検証（`is_valid_uid`） | [12](12_modality_emulator.md) の 6 章 |
| `person_name.py` | 手入力した氏名を PN の形式にする | [12a](12a_web_screens_and_cli.md) |
| `text_safety.py` | 相手から来る値の制御文字を可視化する | [12a](12a_web_screens_and_cli.md) |
| `validation_text.py` | Pydantic の検証エラーを、値を出さずにメッセージにする | [12](12_modality_emulator.md) の 12 章 |

---

## 実装ガイドライン

### Pythonクラス定義場所

クラスとモジュールの対応は「API一覧」の表のとおり。`FileMetaBuilder` と
`SpatialCalculator` は `dicom_writer.py` に、`DICOMBuilder` は `generator.py`
にある。利用側は `from app.core import ...` で import する。

### データモデル

データクラスは `app/core/models.py` に定義。詳細は [03_data_models.md](03_data_models.md) を参照。

### エラーハンドリング

Core Engine内では以下の例外を発生させる：

```python
from app.core.exceptions import (
    UIDGenerationError,
    PixelGenerationError,
    FileMetaError,
    DICOMBuildError
)

# 例
if method not in ["uuid_2_25", "custom_root"]:
    raise UIDGenerationError(f"Invalid method: {method}")
```

### ログ出力

Core Engineはログ出力しない（Pure関数）。Service Layerでログ出力。

---

## テスト方針

### Unit Test

各クラスを独立してテスト：

```python
# tests/core/test_uid_generator.py
def test_generate_study_uid_uuid_2_25():
    uid_gen = UIDGenerator(method="uuid_2_25")
    uid = uid_gen.generate_study_uid()
    
    assert uid.startswith("2.25.")
    assert len(uid) > 10

def test_generate_sop_uid_with_invalid():
    uid_gen = UIDGenerator()
    
    invalid_count = 0
    for _ in range(100):
        uid = uid_gen.generate_sop_uid(allow_invalid=True)
        if ".0" in uid[5:]:  # 先頭以外に.0がある
            invalid_count += 1
    
    assert 5 <= invalid_count <= 15  # 約10%
```

### Dataset 構築のテスト

`DICOMBuilder` は `tests/core/test_dicom_builder.py` で、構築した Dataset の
タグを確認する。Service を含めた生成は `tests/services/test_study_generator.py`、
予約から送信までの流れは `tests/integration/test_modality_flow.py` で確認する。
テストの構成は [development.md](../development.md) の「テスト」を参照。

---

## パフォーマンス目標

| 処理 | 目標時間 |
|------|---------|
| UID生成 | <1ms |
| Pixel Data生成（Simple） | <10ms |
| Pixel Data生成（CT Real） | <50ms |
| DICOM Dataset構築 | <50ms |
| **1画像生成合計** | **<100ms** |

---

## 関連する文書

- [03_data_models.md](03_data_models.md)：データモデル
- [architecture.md](../architecture.md)：Core を使う Service Layer の手順
