# 02. Core レイヤー

DICOM 画像の作成の中核となる Core レイヤー（`app/core/`）のクラスと、その
インターフェースを定める。Core レイヤーは UI レイヤーに依存せず、ログを出力
しない。ログは Service レイヤーが出力する。

## 1. クラスの一覧

| クラス名 | 責務 | モジュール |
|---------|------|-----------|
| `UIDGenerator` | UID の生成 | `uid_generator.py` |
| `PixelGenerator` | ピクセルデータの作成 | `pixel_generator.py` |
| `FileMetaBuilder` | File Meta Information の構築 | `dicom_writer.py` |
| `SpatialCalculator` | 空間座標の計算 | `dicom_writer.py` |
| `DICOMBuilder` | DICOM Dataset の構築 | `generator.py` |
| `AbnormalGenerator` | 異常のデータの作成 | `abnormal_generator.py` |

- 利用側は `from app.core import ...` で import する
- データモデルは `models.py` にある（[03_data_models.md](03_data_models.md)）
- 例外は `exceptions.py` にある（[08_error_handling.md](08_error_handling.md)）
- 上の表に無い Core のモジュールは 8 章にまとめる

## 2. UIDGenerator

DICOM の UID（Study・Series・SOP Instance など）を生成する。

### 2.1 インターフェース

```python
class UIDGenerator:
    def __init__(
        self,
        method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25",
        custom_root: str = "",
        run_scoped: bool = False,
    ): ...
    def generate_study_uid(self) -> str: ...
    def generate_series_uid(self) -> str: ...
    def generate_sop_uid(self, allow_invalid: bool = False) -> str: ...
    def generate_frame_of_reference_uid(self) -> str: ...
    def generate_instance_creator_uid(self) -> str: ...
```

| 引数 | 内容 |
|------|------|
| `method` | `uuid_2_25`（既定）または `custom_root` |
| `custom_root` | `custom_root` のときの根の OID |
| `run_scoped` | True なら、根の後ろに生成器ごとの番号（64 ビットの乱数）を連結する。`StudyGeneratorService` は True で使う |
| `allow_invalid` | True なら、10% の確率で 0 始まりの不正な UID を返す |

- `generate_study_uid` などの各メソッドは、どれも同じ方式で新しい UID を1つ
  返す。スコープ（Study ごとか画像ごとか）は呼ぶ側が決める
- `StudyGeneratorService` は `generate_instance_creator_uid` を使わない。
  Instance Creator UID と Implementation Class UID は、
  `app/services/study_generator.py` の定数（`INSTANCE_CREATOR_UID`・
  `IMPLEMENTATION_CLASS_UID`）で、すべての作成で同じ値を使う
  （PS3.7 D.3.3.2、PS3.10 7.1。[06_dicom_rules.md](06_dicom_rules.md)）

### 2.2 生成の規則

- **UUID 2.25**：`2.25.` の後に `uuid.uuid4().int` の 10 進数を連結する
- **カスタムの根**：`{root}.{counter}` の連番。`run_scoped=True` なら
  `{root}.{run_id}.{counter}`。`run_id` は生成器ごとの 64 ビットの乱数で、
  連番が作成のたびに 1 に戻っても、前の作成の UID と重複する確率は
  無視できる（UID は世界で一意。PS3.5 9。一意性は 2.25 と同じく確率による）
- **根の形式**（PS3.5 9.1）：数字と `.` だけ、2 成分以上、最初の成分は
  0・1・2（0・1 なら 2 番目は 0〜39）、成分の先頭に 0 を置かない（`0` だけの
  成分は可）、64 文字まで。`run_scoped=True` なら、番号と連番を連結しても
  64 文字に収まるよう、根は `CUSTOM_ROOT_MAX_LENGTH`（35 文字）まで
- **0 始まりの不正な UID**：UUID 2.25 では `2.25.0` の後に UUID の数字を続け、
  数字の途中のランダムな位置に `.` を入れる。カスタムの根では
  `{root}.0{counter}` にする
- 次のときは `UIDGenerationError` を送出する：方式が不正、`custom_root` が空
  または根の形式に合わない、根が長すぎる、生成した UID が 64 文字を超える

## 3. PixelGenerator

ピクセルデータ（numpy の配列）を作成する。

### 3.1 インターフェース

```python
class PixelGenerator:
    def generate_simple_text(
        self,
        sop_instance_uid: str,
        width: int = 512,
        height: int = 512,
    ) -> np.ndarray: ...
    def generate_ct_realistic(
        self,
        width: int = 512,
        height: int = 512,
        pattern: Literal["gradient", "circle", "noise"] = "gradient",
        bits_stored: int = 12,
    ) -> np.ndarray: ...
```

| メソッド | 戻り値 | 内容 |
|----------|--------|------|
| `generate_simple_text` | shape=(height, width)、dtype=uint8 | 黒の背景に白の文字で SOP Instance UID を描画する。フォントは DejaVu Sans Mono の 16 ポイント（無ければ Pillow の既定のフォント） |
| `generate_ct_realistic` | shape=(height, width)、dtype=int16 | 下の 3.2 のパターン |

失敗したときと、`pattern` が不正なときは `PixelGenerationError` を送出する。

### 3.2 CT のパターン

値は Bits Stored の符号ありの範囲（0〜上限。12 ビットなら 0〜2047）に収める
（[06_dicom_rules.md](06_dicom_rules.md) の「画素の値の範囲」。PS3.5 8）。

| パターン | 画素の値 |
|----------|----------|
| `gradient` | 左から右へ 0 → 上限（HU -1024 → 12 ビットで 1023） |
| `circle` | 中心の円（半径は幅と高さの小さいほうの 1/4）は 2024（HU 1000、Bone）、周囲は 1064（HU 40、Soft Tissue）。どちらも上限を超えれば上限にする |
| `noise` | 0〜上限の一様な乱数 |

HU への変換は次のとおり。

```text
HU = Pixel Value × Rescale Slope + Rescale Intercept
Rescale Intercept = -1024
Rescale Slope = 1
```

## 4. FileMetaBuilder

File Meta Information（Group 0002）を構築する。

### 4.1 インターフェース

```python
class FileMetaBuilder:
    def build(
        self,
        sop_class_uid: str,
        sop_instance_uid: str,
        transfer_syntax_uid: str,
        implementation_class_uid: str,
        implementation_version_name: str,
    ) -> FileMetaDataset: ...
```

失敗したときは `FileMetaError` を送出する。

### 4.2 設定する属性

| Tag | Attribute Name | Value |
|-----|----------------|-------|
| (0002,0001) | File Meta Information Version | `b'\x00\x01'` |
| (0002,0002) | Media Storage SOP Class UID | `sop_class_uid` |
| (0002,0003) | Media Storage SOP Instance UID | `sop_instance_uid` |
| (0002,0010) | Transfer Syntax UID | `transfer_syntax_uid` |
| (0002,0012) | Implementation Class UID | `implementation_class_uid` |
| (0002,0013) | Implementation Version Name | `implementation_version_name` |

## 5. SpatialCalculator

マルチスライスの空間座標を計算する。

### 5.1 インターフェース

```python
class SpatialCalculator:
    def __init__(
        self,
        slice_thickness: float,
        slice_spacing: float,
        start_z: float = 0.0,
    ): ...
    def calculate(self, slice_index: int) -> SpatialCoordinates: ...
```

- 長さの単位は mm。`slice_index` は 0 始まり
- `slice_index` が負なら `ValueError` を送出する
- 戻り値の `SpatialCoordinates` は [03_data_models.md](03_data_models.md) の
  モデル

### 5.2 計算式

```text
instance_number = slice_index + 1
z = start_z + (slice_index * slice_spacing)
image_position_patient = [0.0, 0.0, z]
slice_location = z
```

## 6. DICOMBuilder

患者・スタディ・シリーズ・画像の値から、CT Image Storage の Dataset を構築する。

### 6.1 インターフェース

```python
class DICOMBuilder:
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
        bits_stored: int = 16,
    ) -> Dataset: ...
```

| 引数 | 内容 |
|------|------|
| `file_meta` | File Meta Information。Media Storage SOP Instance UID が `sop_instance_uid` と異なれば `DICOMBuildError` |
| `specific_character_set` | Specific Character Set。`None` なら、氏名に ASCII 以外の文字があるときだけ `ISO 2022 IR 6\ISO 2022 IR 87` を設定する。値が空で、氏名に ASCII 以外の文字があれば `DICOMBuildError` |
| `use_ideographic`・`use_phonetic` | PN に漢字・カナのコンポーネントグループを入れるか |
| `bits_stored` | Bits Stored（12〜16。PS3.3 C.8.2.1.1.5） |

`DICOMBuilder` は患者・スタディ・シリーズ・画像・空間座標・ピクセルの各タグを
設定するだけで、テンプレートの属性・予約の値・装置プロファイルは重ねない。
重ねる順序は `StudyGeneratorService` が持つ（[architecture.md](../architecture.md)
の「作成の流れ」）。異常値の注入も `DICOMBuilder` は行わない。

失敗はすべて `DICOMBuildError` として送出する。

### 6.2 処理の流れ

1. File Meta の Media Storage SOP Instance UID と `sop_instance_uid` が一致する
   ことを確認し、File Meta を Dataset に設定する
2. Patient Module のタグを設定する。Patient's Age は生年月日と検査日から
   算出する（日本の法律の加齢の規則。
   [ADR-0008](../decisions/0008-patient-age-derived-from-dates.md)）。
   検査日が生年月日より前、または年齢が 0〜999 に収まらなければエラー。
   Patient's Weight・Patient's Size は値があるときだけ設定する
3. General Study Module のタグを設定する。Referring Physician's Name は
   Type 2 なので、Job に無ければ空の値で出力する（PS3.3 C.7.2.1）。
   Study ID は空
4. General Series Module のタグを設定する（Modality は `CT`、Patient Position
   の既定値は `HFS`）
5. Frame of Reference Module のタグを設定する（Position Reference Indicator
   は空）
6. General Image Module・CT Image Module のタグを設定する（Image Type の
   既定値 `ORIGINAL\PRIMARY\AXIAL`、Acquisition Number、Content Date・
   Content Time。[06_dicom_rules.md](06_dicom_rules.md) の
   「CT Image の必須の属性」）
7. SOP Common Module のタグを設定する（SOP Class UID は File Meta の
   Media Storage SOP Class UID）
8. 空間座標のタグを設定する（Image Position・Image Orientation・
   Slice Location・Slice Thickness・Pixel Spacing。DS は 16 文字以内。
   [06_dicom_rules.md](06_dicom_rules.md) の「DS の書き方」）
9. Pixel Data を設定する（6.3）
10. Transfer Syntax を検証する。作成できるのは Implicit VR Little Endian と
    Explicit VR Little Endian だけで、Explicit VR Big Endian（廃止。PS3.5 A.3）
    とそのほかの値はエラーにする

### 6.3 Pixel Data

| 属性 | 値 |
|------|----|
| Samples per Pixel | 1 |
| Photometric Interpretation | `MONOCHROME2` |
| Bits Allocated | 16 |
| Bits Stored・High Bit | `bits_stored`・`bits_stored - 1` |
| Pixel Representation | 1（符号あり） |
| Rescale Intercept・Rescale Slope | `-1024`・`1` |
| Window Center・Window Width | `40\400`・`400\1500` |

- uint8 の画素（Simple Text）は、0〜255 を 0〜Bits Stored の上限に広げて
  int16 にする
- int16 の画素が Bits Stored の符号ありの範囲に収まらなければエラー
- uint8・int16 以外の dtype はエラー

## 7. AbnormalGenerator

異常のデータ（不正な値）を作成する。

### 7.1 インターフェース

```python
class AbnormalGenerator:
    def __init__(self, level: Literal["none", "mild", "moderate", "severe"]): ...
    @property
    def level(self) -> str: ...
    def apply_abnormal_value(
        self,
        tag_name: str,
        normal_value: Any,
        vr: str,
        tag_type: int,
        max_length: int | None = None,
    ) -> Any | None: ...

def apply_abnormal_to_dataset(
    dataset: Dataset, generator: AbnormalGenerator
) -> None: ...
```

- `level` が上の4つ以外なら `GenerationError` を送出する
- `apply_abnormal_value` は、壊した値を返す。`None` はタグの欠落を表す

### 7.2 レベルごとの動作

`apply_abnormal_value` の動作は次のとおり。

| Level | 動作 |
|-------|------|
| `none` | 正常値をそのまま返す |
| `mild` | `max_length` があれば、その 2 倍の長さのランダムな文字列。無ければ VR ごとに、DA は `INVALID_DATE`、TM は `INVALID_TIME`、IS は `NOT_A_NUMBER`、DS は `NOT_DECIMAL`、CS は `invalid_cs!`、UI は 64 文字を超える UID。そのほかの VR は正常値の後にランダムな 8 文字を連結する |
| `moderate` | Type 1 は `None`。Type 2 は 50% の確率で `None`。それ以外は、UI なら `0.2.25.` で始まる 0 始まりの UID、UI 以外は `mild` と同じ |
| `severe` | Type 1・2 は `None`。Type 3 は 50% の確率で `None`。それ以外は、UI なら `INVALID_UID_XXXX`、UI 以外は型の異なる値（数値なら `INVALID_TYPE`、それ以外なら `12345`） |

壊し方の一部は乱数で決まる（`random`）。同じレベルでも画像ごとに値が異なる。

### 7.3 Dataset への適用

`apply_abnormal_to_dataset(dataset, generator)` が、次の表のタグのうち Dataset
にあるものに `apply_abnormal_value` を適用する。表に無いタグは壊さない。
壊した値が `None` ならタグを削除する。`none` では何も変えない。

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

- 表のタグは Type 1・2 だけなので、`moderate` では Type 1 のタグ（UI を
  含む）を削除し、Type 2 のタグは半数を削除して残りを `mild` と同じ形で壊す。
  `severe` では表のタグをすべて削除する
- `severe` は、この表の処理に加えて Pixel Data を削除する
- File Meta は壊さない。Dataset 側の SOP Instance UID だけが File Meta と
  食い違うことがある
- IS・DS の不正な文字列は、pydicom の検証を通過しないので、生の値として入れる。
  文字列の VR に入る整数は、文字列にして入れる
- Study Instance UID を削除した画像でも撮影の結果を返せるよう、画像から Study UID
  を読み取る処理は、タグが無ければ空にする
- **定義の範囲**：異常のデータで作成する規格の違反は、上の表のタグの壊し方・
  Pixel Data の削除・`allow_invalid_sop_uid` の SOP Instance UID の 0 始まり
  だけ。Transfer Syntax・画素値・File Meta は定義に含まれない（廃止された
  Explicit VR Big Endian は異常のデータでも作成しない）。通常の経路の規格の
  チェックは、この定義の壊し方を妨げない（[06_dicom_rules.md](06_dicom_rules.md)
  の「通常の経路と異常のデータの経路」、
  [ADR-0014](../decisions/0014-separate-normal-and-abnormal-paths.md)）

### 7.4 作成への組み込み

`StudyGeneratorService.generate` は、`abnormal.level` で作成した
`AbnormalGenerator` を、Dataset を組み立てた後（テンプレート・予約・
装置プロファイルを適用した後）に、画像1枚ごとに適用する。`generate` を経由する
経路（`generate`・`quick`・モダリティエミュレーターの撮影・GUI）はすべてこの
処理を経由する。`level` が `none`（既定）のときは何も変えない。

`abnormal.allow_invalid_sop_uid`（SOP Instance UID の 0 始まり）は `level` とは
別の設定で、`level` に関わらず有効。

レベルを指定する場所は次のとおり。

- Job YAML の `abnormal.level`
- `generate`・`quick` の `--abnormal-level`（`generate` では CLI が Job YAML
  より優先）
- モダリティエミュレーターの `exam --abnormal-level` と、画面の「異常のデータ」

## 8. Core のそのほかのモジュール

モダリティエミュレーター（[12_modality_emulator.md](12_modality_emulator.md)）と
装置プロファイル（[13_device_profiles.md](13_device_profiles.md)）のための、
Pure な処理のモジュール。どれも通信・ファイル・ログを使わない。ここでは役割だけを
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

## 9. テスト

| ファイル | 対象 |
|---------|------|
| `tests/core/test_uid_generator.py`・`test_uid_custom_root.py` | `UIDGenerator` |
| `tests/core/test_pixel_generator.py`・`test_ct_bits.py` | `PixelGenerator` と Bits Stored |
| `tests/core/test_dicom_writer.py` | `FileMetaBuilder`・`SpatialCalculator` |
| `tests/core/test_dicom_builder.py`・`test_ct_image_conformance.py` | `DICOMBuilder` が構築した Dataset のタグ |
| `tests/core/test_abnormal_generator.py` | `AbnormalGenerator`・`apply_abnormal_to_dataset` |
| `tests/services/test_study_generator.py` | Service を含めた作成 |
| `tests/integration/test_modality_flow.py` | 予約から送信までの流れ |

テストの構成は [development.md](../development.md) の「テスト」を参照。

## 10. 関連する文書

- [03_data_models.md](03_data_models.md)：データモデル
- [architecture.md](../architecture.md)：Core レイヤーを使う DICOM 画像の作成の流れ
