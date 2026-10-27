# 06. DICOM の規則

DTG が作成する DICOM ファイルの属性・値・符号化の規則を定める。値・Type・
長さ・文字コードは原典（dicom.nema.org の PS3.x）で確認し、規格の節番号を
書く。Type の定義は PS3.5 7.4、VR の定義は PS3.5 6.2 の表 6.2-1 による。

## 1. 前提

DTG は DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。
仕様を変えるときも原典（PS3.x、IHE の Technical Framework）に合わせる。

### 1.1 通常の経路と異常のデータの経路

DTG は、あえて DICOM の規格に違反したデータを作成する機能（異常のデータ）を
持つ。規格に違反しないという前提は、通常の経路にだけ適用する
（[ADR-0014](../decisions/0014-separate-normal-and-abnormal-paths.md)）。

- **通常の経路**：異常のデータのレベルが `none` で、
  `abnormal.allow_invalid_sop_uid` を使わない作成。Job・テンプレート・
  装置プロファイル・予約・画面と CLI の入力は、規格に合う値だけを受け付け、
  合わない値は作成の前に拒否する。作成する画像は規格どおりにする
- **異常のデータの経路**：`abnormal.level` が `mild`・`moderate`・`severe`
  のときと、`abnormal.allow_invalid_sop_uid`。規格に違反した値を作成すること
  そのものが目的で、規格の前提の対象外。何を壊すかの定義は
  [spec/02 の AbnormalGenerator](02_core_engine.md)（壊すタグの表・
  Pixel Data の削除・SOP Instance UID の 0 始まり）にあり、定義した
  壊し方を、通常の経路のチェックで妨げない
- 異常のデータは、組み立てた Dataset に最後に適用する（spec/02）。
  通常の経路のチェック（Type 1 の属性・画素値の範囲・DS の長さ・UID の形式・
  文字コード・入力の `\`）は、適用前の値か、定義に無い入力にかかるので、
  定義した壊し方と衝突しない
- 定義に無い違反（例：廃止された Transfer Syntax の Explicit VR Big Endian）は、
  異常のデータの経路でも作成しない。作成できるようにするときは、先に spec/02 の
  定義に追加する

### 1.2 装置のコンフォーマンスステートメントからの再現

特定の装置の DICOM の出力方法（製造者・型名・ソフトウェアバージョン・文字コードの
組み合わせ・必ず出力する属性・空で出力する属性・プライベートタグ・Transfer
Syntax）は、その装置のコンフォーマンスステートメント（DICOM PS3.2）を読んで
**装置プロファイル**に転記し、モダリティテンプレートの上に重ねて再現する。
形式・転記の手順・配置場所は [spec/13_device_profiles.md](13_device_profiles.md)
にある。実在の装置のプロファイルは公開のリポジトリに置かない（ADR-0012）。

## 2. File Meta Information

File Meta Information（Group 0002）は `FileMetaBuilder`
（`app/core/dicom_writer.py`）が組み立てる（PS3.10 7.1）。

| Tag | Attribute Name | Type | 値 |
|-----|----------------|------|----|
| (0002,0001) | File Meta Information Version | 1 | `00H 01H`（固定） |
| (0002,0002) | Media Storage SOP Class UID | 1 | モダリティテンプレートの `file_meta.media_storage_sop_class_uid`（既定は CT Image Storage `1.2.840.10008.5.1.4.1.1.2`）。装置プロファイルを使うときは、プロファイルの `storage.sop_classes` の最初の値 |
| (0002,0003) | Media Storage SOP Instance UID | 1 | 画像の SOP Instance UID と同じ値。異なれば `DICOMBuildError` |
| (0002,0010) | Transfer Syntax UID | 1 | Job の `transfer_syntax.uid`（9 章） |
| (0002,0012) | Implementation Class UID | 1 | DTG の固定の UID（`IMPLEMENTATION_CLASS_UID`。同じ実装は同じ UID。PS3.7 D.3.3.2、PS3.10 7.1） |
| (0002,0013) | Implementation Version Name | 3 | モダリティテンプレートの `file_meta.implementation_version_name`（既定 `DICOM_GEN_1.1`）。装置プロファイルの `device.implementation_version_name` があれば、その値 |

- File Meta Information Group Length (0002,0000) とプリアンブルは、
  書き出すときに pydicom が付ける（`pydicom.dcmwrite` の
  `enforce_file_format=True`）
- モダリティテンプレートの `file_meta.transfer_syntax_uid` は読まない。
  Transfer Syntax は Job の値だけで決まる

## 3. UID の生成

### 3.1 UID の種類と範囲

| UID | 範囲 | 生成する時点 | 備考 |
|-----|------|--------------|------|
| Study Instance UID | Study | 作成の開始時に 1 回 | 予約からの撮影で予約に値があれば、その値を使う（spec/12） |
| Series Instance UID | Series | シリーズごとに 1 回 | |
| SOP Instance UID | Instance | 画像ごと | |
| Frame of Reference UID | Study | 作成の開始時に 1 回 | 同じ Study のすべてのシリーズで共通（空間座標を共有するため） |
| Instance Creator UID | 固定 | 定数（`INSTANCE_CREATOR_UID`） | DTG が作成するすべての画像で共通 |

生成の方式は Job の `uid_method` で選ぶ（`uuid_2_25` が既定）。生成は
`UIDGenerator`（`app/core/uid_generator.py`）が行う。

Implementation Class UID と Instance Creator UID は、固定の値（`app/services/study_generator.py`
の `IMPLEMENTATION_CLASS_UID`・`INSTANCE_CREATOR_UID`）で、どちらも 2.25（UUID 派生）の
形である。PS3.5 B.2 は、設計時に決める固定の UID には、UUID 派生を通常は勧めていない。
製品として配るときは、登録した根（例：IANA の Private Enterprise Number）の下の UID に
替える予定である（このバージョンのコードは変えない）。

### 3.2 UUID 2.25 方式

形式は `2.25.{UUID の 128 ビットの整数の 10 進表記}`（PS3.5 B.2）。UUID は
バージョン 4（乱数）を使う。

例：`2.25.113059749145936325402354257176981405696`

### 3.3 カスタム Root 方式

形式は `{custom_root}.{作成ごとの番号}.{連番}`。ルートは Job の
`uid_custom_root` で指定する。

- UID は世界で一意でなければならない（PS3.5 9）。連番は作成のたびに 1 に
  戻るので、作成ごとの番号（64 ビットの乱数、20 桁まで）をルートの後ろに
  連結し、前の作成の UID と重複する確率を無視できるほど小さくする
  （2.25 の UUID と同じく、確率による一意性）
- 連番は、1 回の作成の中で Study・Frame of Reference・Series・SOP Instance
  の順に生成するたびに 1 ずつ増える
- ルートは PS3.5 9.1 の形式：数字と `.` だけ、2 成分以上、最初の成分は 0・1・2
  （0・1 なら 2 番目は 0〜39。ITU-T X.660）、成分の先頭に 0 を置かない
  （`0` だけの成分は可）。UID は 64 文字までなので、ルートは 35 文字まで。
  外れれば `UIDGenerationError`
- ルートは自分の組織に割り当てられたものを使う。他の組織のルートを使わない

### 3.4 SOP Instance UID の不正な値（異常のデータ）

Job の `abnormal.allow_invalid_sop_uid` が `true` のとき、SOP Instance UID を
10% の確率で、先頭が 0 の成分を含む値にする（PS3.5 9.1 に違反する）。
確率は固定で、Job の `abnormal.invalid_sop_uid_probability` は使わない。

| 方式 | 不正な値の形 |
|------|--------------|
| `uuid_2_25` | `2.25.0{UUID の整数の前半}.{後半}`（新しい UUID を任意の位置で 2 つに分ける） |
| `custom_root` | `{custom_root}.{作成ごとの番号}.0{連番}` |

```text
正常: 2.25.123456789012345678901234567890
不正: 2.25.0123456.789012345678901234567890
```

## 4. Pixel Data

### 4.1 モード

Job の `pixel_spec.mode` で選ぶ（[ADR-0005](../decisions/0005-pixel-modes.md)・
[ADR-0033](../decisions/0033-phantom-pixels.md)）。どのモードも CT のシリーズでは
CT Image（PS3.3 C.8.2.1）の画素として書く（MR は 5.2、PET は 5.4）。既定は
`ct_realistic` で、`phantom` は選んだときだけ使う。

| モード | 用途 | Bits Allocated | Bits Stored | Pixel Representation | 内容 |
|--------|------|----------------|-------------|----------------------|------|
| `simple_text` | 簡易確認 | 16 | 12（固定） | 1（符号あり） | SOP Instance UID の文字列 |
| `ct_realistic` | ビューアでの表示 | 16 | 12〜16（既定 12） | 1（符号あり） | HU 値のパターン |
| `phantom` | スライスを送る・MPR の試験 | 16 | 12〜16（既定 12） | 1（符号あり） | スライスの位置で断面が変わる図形と位置の目印（4.6） |

### 4.2 画素の属性

`DICOMBuilder`（`app/core/generator.py`）が、CT のシリーズにはどのモードでも次の値を書く。

| Tag | Attribute Name | 値 |
|-----|----------------|----|
| (0028,0002) | Samples per Pixel | 1 |
| (0028,0004) | Photometric Interpretation | `MONOCHROME2` |
| (0028,0010) | Rows | `pixel_spec.height`（既定 512） |
| (0028,0011) | Columns | `pixel_spec.width`（既定 512） |
| (0028,0100) | Bits Allocated | 16 |
| (0028,0101) | Bits Stored | 4.1 の表のとおり |
| (0028,0102) | High Bit | Bits Stored − 1 |
| (0028,0103) | Pixel Representation | 1 |
| (0028,1050) | Window Center | `40\400` |
| (0028,1051) | Window Width | `400\1500` |
| (0028,1052) | Rescale Intercept | `-1024` |
| (0028,1053) | Rescale Slope | `1` |

CT Image では Bits Allocated は 16、Bits Stored は 12〜16、Rescale
Intercept・Slope は Type 1（PS3.3 C.8.2.1.1.4・C.8.2.1.1.5）。Bits Stored が
この範囲の外なら `DICOMBuildError` になる。画素の値と HU 値の関係は次のとおり。

```text
HU = Pixel Value × Rescale Slope + Rescale Intercept
```

モダリティテンプレートの `ct_image.rescale_intercept`・`rescale_slope` と
`window_presets` は読まない。上の値は固定である。

### 4.3 simple_text

1. Pillow で 8 ビットのグレースケールの画像を作成する。背景は 0（黒）、
   文字は 255（白）
2. SOP Instance UID を、幅 10 ピクセルあたり 1 文字で折り返し、x = 10、
   y = 高さの 1/4 から 20 ピクセルの行間で描く。フォントは DejaVu Sans Mono
   の 16 ポイントで、無ければ Pillow の既定のフォント
3. `DICOMBuilder` が 0〜255 を 0〜2047 に線形に広げ（四捨五入）、Bits Stored
   12 の CT の画素として書く。背景は画素 0（HU −1024）、文字は画素 2047
   （HU 1023）になる

Job の `pixel_spec.background_color`・`text_color`・`font_size` は受け付けるが、
画像には反映しない。

### 4.4 ct_realistic

`pixel_spec.pattern` で次の 3 つから選ぶ（既定 `gradient`）。Bits Stored の
上限は 2^(Bits Stored − 1) − 1（12 ビットなら 2047）。

| パターン | 画素の値 |
|----------|----------|
| `gradient` | 左端 0 から右端の上限まで、列ごとに線形に増やす（12 ビットで HU −1024〜1023） |
| `circle` | 中心に半径 min(幅, 高さ)/4 の円。円の内側は 2024（HU 1000、骨）、外側は 1064（HU 40、軟部組織）。上限を超える値は上限に収める |
| `noise` | 0 から上限までの一様な乱数 |

### 4.5 画素の値の範囲

Pixel Representation 1 の画素は、Bits Stored のビット数の 2 の補数で表す
（PS3.3 C.7.6.3、PS3.5 8）。値は −2^(Bits Stored − 1) 〜
2^(Bits Stored − 1) − 1 に収める。12 ビットなら −2048〜2047 で、DTG は
0〜2047（HU −1024〜1023）を使う。範囲を超える値は、読み込む側が High Bit で
符号拡張するため別の値に変わる（12 ビットの 2048 は −2048）。
`DICOMBuilder` は範囲を超える画素を `DICOMBuildError` で拒否する。

### 4.6 phantom

画素の患者座標で3次元の図形を評価し、スライスの位置で断面の大きさが変わる画像を
作る（`app/core/phantom.py`。[ADR-0033](../decisions/0033-phantom-pixels.md)）。
画素に文字は描かない。

**図形を決める**：図形（回転楕円体1つ）は、1回の撮影（同じ Frame of Reference UID
の画像の組）で一度だけ患者座標（mm）で決め、その撮影の全シリーズで使う。

| 値 | 決め方 |
|----|--------|
| 中心の x・y | 軸位の視野の中央。視野は CT が 列数 × 0.5 mm と 行数 × 0.5 mm、MR が 240 mm |
| x・y の半径 | 視野の 0.4 倍 |
| 中心の z と z の半径 | 位置の範囲がいちばん長い軸位のシリーズ（CT の軸位、MR の `plane: axial` の撮像・計算で作った画像）の範囲の中央と、範囲の長さの 0.55 倍。軸位が無ければ、今の冠状断・矢状断が写す範囲（z が 0 から視野の高さだけ下）の中央と、視野の高さの 0.55 倍 |

**画素を作る**：各画素の中心の患者座標を、Image Position (Patient)・Image
Orientation (Patient)・Pixel Spacing から計算する（PS3.3 C.7.6.2.1.1）。回転楕円体の
内側を図形の値、外側を背景の値にする。CT の位置決め（投影の画像）は、画像の面に
垂直な向きの座標を図形の中心に置いて評価する（回転楕円体の影の形）。MR の
位置決めは断層の画像として評価する。

**位置の目印**：どの画像にも、1辺が画像の小さいほうの辺の 0.04 倍（2 画素以上）の
正方形を、画像の中心から 0.3 倍の円の上に目印の値で描く。角度はシリーズの中の
番号 k（0 始まり）と画像の数 n から 360° × k / n で、0° は中心の右、番号が進むと
上へ回る。回転楕円体は中央に対して対称なので、中央から同じ距離の2枚は断面の
大きさが同じになるが、目印の位置で見分けられる。目印は3次元の図形に含めない。

**値**：区分ごとに一定の値にする。ノイズ・ぼかしは足さない。

| 区分 | CT（HU。格納値は HU + 1024） | MR（符号なしの Bits Stored の上限に対する割合。四捨五入） |
|------|------------------------------|----------------------------------------------------------|
| 背景 | −1000 | 0 |
| 図形 | 40 | 0.40 |
| 位置の目印 | 1000 | 0.90 |

Rescale・Window の値は、CT は 4.2、MR は 5.2 のとおり。

**画像の位置**：冠状断・矢状断と CT の位置決めの Image Position (Patient) の z を、
軸位の範囲の上端（いちばん長い軸位のシリーズの最後の画像の z）にする。軸位が
無ければ 0 のまま。MR の冠状断・矢状断の断面（`three_plane` を含む）も同じ。
ほかのモードの位置は 5.1 のまま変えない。

**偽物の印**：図形で画素を作った画像（CT の位置決め・軸位・冠状断・矢状断と MR の
画像）には、装置のプロファイル（[spec/13](13_device_profiles.md)）を当てた後に次を
書き、プロファイルの値より優先する。線量の画面・線量の報告の SR・PET/CT の PT の
シリーズには書かない。ほかのモードの画像にも書かない。

| Tag | Attribute Name | 値 |
|-----|----------------|----|
| (0008,0070) | Manufacturer | `DTG SYNTHETIC` |
| (0008,1090) | Manufacturer's Model Name | `DTG SYNTHETIC` |
| (0020,4000) | Image Comments | `SYNTHETIC TEST DATA` |
| (0028,0301) | Burned In Annotation | `NO` |
| (0028,0302) | Recognizable Visual Features | `NO` |

Burned In Annotation と Recognizable Visual Features は General Image Module の
Type 3（PS3.3 C.7.6.1）。Software Versions・Device Serial Number・Station Name・
プライベートタグは装置のプロファイルの値のまま。異常のデータ（1.1）はこの後に
当てる。

**PET/CT**：`phantom` でも PT のシリーズは図形にせず、`ct_realistic` の
`gradient` の画素で作る（5.4）。

## 5. CT Image の必須の属性

CT Image IOD（PS3.3 A.3）の Type 1・2・2C の属性のうち、Job・テンプレート・
予約から値が来ないものは、`DICOMBuilder` が次の既定値で必ず出力する。
装置プロファイルの `attributes.set` で変更でき、`omit` では削除できない。
Type 1 の Image Type は `empty` と空の `set` でも空にできない
（spec/13 の 3.3）。

| Tag | Attribute Name | Module | Type | 既定値 | 規格の節 |
|-----|----------------|--------|------|--------|----------|
| (0008,0008) | Image Type | CT Image | 1 | `ORIGINAL\PRIMARY\AXIAL` | PS3.3 C.8.2.1.1.1 |
| (0018,5100) | Patient Position | General Series | 2C（CT Image Storage では必須） | `HFS` | PS3.3 C.7.3.1、C.7.3.1.1.2 |
| (0020,1040) | Position Reference Indicator | Frame of Reference | 2 | 空 | PS3.3 C.7.4.1、C.7.4.1.1.2 |

CT の Image Type の値 3 の Defined Terms は `AXIAL` と `LOCALIZER`
（C.8.2.1.1.1。`AXIAL` は断層の画像を指し、横断に限らない）。DTG は
断層の画像を作成するので、既定を `AXIAL` にする。

### 5.1 撮影のルーチンのシリーズの種類

撮影のルーチン（[ADR-0025](../decisions/0025-exam-routines.md)）で撮ったシリーズは、
種類ごとに次の値にする。手で入れたシリーズは軸位で、上の表のとおり。画素の
モードが `phantom` のときは、位置決め・冠状断・矢状断の画像の位置の z を軸位の
範囲の上端にする（4.6）。

| 種類 | SOP Class | Image Type | Image Orientation (Patient) | 画像の位置 |
|------|-----------|------------|-----------------------------|------------|
| 位置決め | CT Image Storage | `ORIGINAL\PRIMARY\LOCALIZER` | 正面 `1\0\0\0\0\-1`、側面 `0\1\0\0\0\-1`（ルーチンの `views` を画像ごとに繰り返す） | 原点 |
| 軸位 | CT Image Storage | `ORIGINAL\PRIMARY\AXIAL` | `1\0\0\0\1\0` | z をスライス厚ずつ進める |
| 冠状断 | CT Image Storage | `DERIVED\SECONDARY\AXIAL` | `1\0\0\0\0\-1` | y（前後）をスライス厚ずつ進める |
| 矢状断 | CT Image Storage | `DERIVED\SECONDARY\AXIAL` | `0\1\0\0\0\-1` | x（左右）をスライス厚ずつ進める |
| 線量の画面 | Secondary Capture Image Storage（1.2.840.10008.5.1.4.1.1.7） | `DERIVED\SECONDARY` | 無し | 無し |

- Series Description (0008,103E) と Protocol Name (0018,1030) はルーチンの値。
  Slice Thickness (0018,0050) と画像の位置の間隔はルーチンの `slice_thickness`
- 造影のシリーズ（`contrast: true`）は Contrast/Bolus Agent (0018,0010) に
  `IOPAMIDOL`（架空の値）を入れる（Contrast/Bolus Module。PS3.3 C.7.6.4）
- 線量の画面（Secondary Capture Image IOD。PS3.3 A.8.1）：Modality は `CT`、
  Conversion Type (0008,0064) は `WSD`（PS3.3 C.8.6.1）、Patient Orientation
  (0020,0020) は空（Type 2C。PS3.3 C.7.6.1）。画素は 8 ビットの MONOCHROME2 で、
  位置決めと軸位のシリーズごとの架空の CTDIvol・DLP を描く。Frame of Reference・
  Image Plane・CT Image の属性は持たない（装置のプロファイルが足しても外す）
- Image Type の値 4 と Source Image Sequence は付けない。RDSR は作らない

### 5.2 MR Image の属性

画像を作れるモダリティは CT・MR・PT（5.4）だけ。テンプレートのモダリティ
（`info.modality`）がほかの値（CR・US など）なら、画像を作る前に断る
（`DICOMValidationError`）。前は CT・MR 以外のテンプレートでも CT Image として作っていた。

MR のシリーズ（[ADR-0030](../decisions/0030-mr-images.md)）は MR Image Storage
（1.2.840.10008.5.1.4.1.1.4）で作る。MR Image IOD（PS3.3 A.4）の必須のモジュールを
持ち、Modality (0008,0060) は `MR`。MR Image Module（PS3.3 C.8.3.1）は次の値にする。

| 属性 | Type | 値 |
|------|------|----|
| Image Type (0008,0008) | 1 | 位置決め・撮像は `ORIGINAL\PRIMARY\M\ND`、計算で作った画像は `DERIVED\SECONDARY` |
| Samples per Pixel / Photometric Interpretation | 1 | `1` / `MONOCHROME2` |
| Bits Allocated / Bits Stored / High Bit | 1 | `16` / ジョブの Bits Stored（12〜16、既定 12）/ Bits Stored − 1。Pixel Representation は `0`（符号なし） |
| Scanning Sequence (0018,0020) | 1 | ルーチンの `sequence`（SE・IR・GR・EP） |
| Sequence Variant (0018,0021) | 1 | SE と IR は `SK`、GR は `SP`、EP は `NONE` |
| Scan Options (0018,0022) / MR Acquisition Type (0018,0023) | 2 | 空 / ルーチンの `acquisition_type`（2D・3D） |
| Repetition Time (0018,0080) | 2C | 常に入れる（SE 3000、IR 9000、GR 600、EP 5000 ms。架空） |
| Echo Time (0018,0081) / Echo Train Length (0018,0091) | 2 | SE 90 ms・15、IR 100 ms・15、GR 15 ms・1、EP 80 ms・1 |
| Inversion Time (0018,0082) | 2C | Scanning Sequence が IR のときだけ 2500 ms |

- Frame of Reference UID は検査で共通（ほかのシリーズと同じ空間）。Image Position
  (Patient)・Image Orientation (Patient)・Slice Location・Slice Thickness・Spacing
  Between Slices を持つ。画像の間隔は スライス厚 + ルーチンの `spacing`
- 断面の向きと進める軸は CT の冠状断・矢状断・軸位と同じ（5.1）。`three_plane` は
  画像を3等分して axial・coronal・sagittal の順に割り当て（余りは最後の断面）、
  それぞれ断面の中で位置を進める
- Pixel Spacing (0028,0030) は視野 240 mm（架空）を画素数で割った値
- Window Center / Width (0028,1050・1051) は画素の上限の 1/4 と 1/2。Rescale
  Intercept・Slope、KVP などの CT の属性は持たない
- テンプレートの `mr_image`（Magnetic Field Strength・Imaged Nucleus・Receive Coil
  Name）と `general_equipment` を重ねる

### 5.3 線量の報告の SR

CT の検査の線量の報告は、5.1 の線量の画面（Secondary Capture）のほかに、
X-Ray Radiation Dose SR（1.2.840.10008.5.1.4.1.1.88.67。[ADR-0031](../decisions/0031-dose-report-sr.md)）
でも作れる。種類は `dose_sr`、Modality (0008,0060) は `SR`。

| モジュール | 値 |
|------------|----|
| SR Document Series（PS3.3 C.17.1） | Modality `SR`、Series Number、Referenced Performed Procedure Step Sequence（Type 2。MPPS を使えば予約の値で入る） |
| Enhanced General Equipment（C.7.5.2） | Manufacturer・Model Name・Software Versions はテンプレート、Device Serial Number は `DTG0001`（装置のプロファイルが決めれば上書き）。Device UID (0018,1002) は Instance Creator UID と同じ |
| SR Document General（C.17.2） | Completion Flag `COMPLETE`、Verification Flag `UNVERIFIED`、Content Date/Time は検査の日時、Performed Procedure Code Sequence は空。予約の撮影では Referenced Request Sequence (0040,A370)（Type 1C。下）。Current Requested Procedure Evidence Sequence (0040,A375)（Type 1C）に、同じ撮影で作った画像（線量の画面を含む。SR は含めない）を Study・Series ごとに入れる |
| SR Document Content（C.17.3） | TID 10011 の木（下） |

内容の木（PS3.16 TID 10011・10012・10013・10014。必須の行と、条件を満たして必須になる行）：

- 根：CONTAINER「X-Ray Radiation Dose Report」(113701, DCM)。Content Template
  Sequence は `DCMR`・`10011`。以下の行は、この順で並べる
- HAS CONCEPT MOD：Procedure reported (121058, DCM) = Computed Tomography X-Ray
  (77477000, SCT)。その下に HAS CONCEPT MOD の Has Intent (363703001, SCT) =
  Diagnostic Intent (261004008, SCT。CID 3629)
- HAS OBS CONTEXT：Observer Type (121005, DCM) = Device、Device Observer UID
  (121012, DCM)、Start of X-Ray Irradiation (113809, DCM)・End of X-Ray
  Irradiation (113810, DCM)（検査の日時から、撮影1回につき 30 秒後まで）、
  Scope of Accumulation (113705, DCM) = Study (113014, DCM) と、その下の
  HAS PROPERTIES の Study Instance UID (110180, DCM)
- CONTAINS：CT Accumulated Dose Data (113811, DCM)（撮影の数 {events} と、DLP の合計
  mGy.cm）、撮影ごとに CT Acquisition (113819, DCM)、最後に Source of Dose Information
  (113854, DCM) = Automated Data Collection (113856, DCM)
- 撮影（CT Acquisition）：Target Region = Entire body (38266002, SCT)、CT Acquisition
  Type（CID 10013。位置決めは Constant Angle Acquisition (113805, DCM)、軸位は Spiral
  Acquisition (116152004, SCT)）、Irradiation Event UID、CT Acquisition Parameters
  （Exposure Time・Scanning Length（画像数 × 画像の間隔）・Nominal Single/Total
  Collimation Width・Number of X-Ray Sources・CT X-Ray Source Parameters（KVP・Maximum
  X-Ray Tube Current・X-Ray Tube Current。軸位だけ Exposure Time per Rotation）。軸位
  だけ Exposed Range と Pitch Factor）、CT Dose（Mean CTDIvol・CTDIw Phantom Type =
  IEC 320mm Body CT Dosimetry Phantom (113691, DCM。CID 4053)・DLP）
- TID 10013 の条件：Exposure Time per Rotation（行 19）と CT Dose（行 21）は「Constant
  Angle でなければ必須」の IF の条件で、Constant Angle でも入れてよい（PS3.16 6.1.8）。
  位置決めには Exposure Time per Rotation を入れない（管球が回らない）。CT Dose は
  位置決めにも入れ、TID 10012 の DLP の合計（撮影ごとの DLP の和）を線量の画面と
  そろえる。Pitch Factor（行 12）は Spiral か Sequenced のとき、Exposed Range（TID 10014
  の行 3）は Spiral のときだけ（IFF）。CT Dose Check Details（TID 10015。行 35）は、
  中の2つの容器が「装置が線量の警告・通知を持つとき」の条件で、DTG は持たないので空
- 撮影になるのは、同じ検査の CT の位置決めと軸位のシリーズ（線量の画面と同じ。MR の
  位置決めは含めない）。CTDIvol と DLP は線量の画面と同じ架空の値で、合計も一致する。
  撮影が1つも無ければ作らない
- SR のシリーズは、ほかのシリーズを全部作った後に作る（Job の並びの途中に書いて
  あっても最後のファイルになる。シリーズ番号は書いたとおり）
- Referenced Request Sequence の項目（Referenced Request Macro。PS3.3 C.17-3c）：
  Study Instance UID、Referenced Study Sequence（予約の値。無ければ空）、Accession
  Number、Issuer of Accession Number Sequence（予約にあれば）、Placer・Filler Order
  Number（予約の C-FIND で受けないので空。Type 2）、Requested Procedure ID・
  Description、Requested Procedure Code Sequence（予約の値。無ければ空）、Reason for
  the Requested Procedure（予約にあれば）。予約なし（緊急の患者）では入れない
- 画像に入れる Request Attributes Sequence と、Performed Procedure Step の ID・開始の
  日時・説明は General Series Module（C.7.3.1）の属性で、SR の IOD（A.35.8）に無いので
  SR には入れない
- 数値は NUM、単位は UCUM（`mGy`・`mGy.cm`・`kV`・`mA`・`s`・`mm`・`{events}`・
  `{ratio}`・`{X-Ray sources}`）。文字はすべて ASCII
- 画素・Frame of Reference は持たない。装置のプロファイルが足した画像の属性は外す

### 5.4 PET Image の属性

PET/CT のテンプレート（モダリティ `PT`。[ADR-0032](../decisions/0032-pet-ct-studies.md)）の
PT のシリーズは、Positron Emission Tomography Image Storage
（1.2.840.10008.5.1.4.1.1.128）で作る。Modality (0008,0060) は `PT`。同じ検査の CT の
シリーズは 5.1 のとおり CT Image Storage で、Study Instance UID と Frame of Reference
UID を PT と共有する。PET Image IOD（PS3.3 A.21）の必須のモジュールを持ち、値は次の
とおり（架空）。

| 属性 | Type | 値 |
|------|------|----|
| Series Date / Time (0008,0021・0031) | 1 | 検査の日時（PET では Type 1。C.8.9.1.1.2） |
| Units (0054,1001) | 1 | `BQML` |
| Counts Source (0054,1002) | 1 | `EMISSION` |
| Series Type (0054,1000) | 1 | `WHOLE BODY\IMAGE` |
| Number of Slices (0054,0081) | 1 | シリーズの画像数 |
| Corrected Image (0028,0051) | 2 | 補正あり（`pet_ac`）：`DECY\ATTN\SCAT\DTIM\RAN\NORM`、補正なし（`pet_nac`）：`DECY\DTIM\RAN\NORM` |
| Decay Correction (0054,1102) | 1 | `START` |
| Collimator Type (0018,1181) | 2 | `NONE` |
| Radiopharmaceutical Information Sequence (0054,0016) | 2 | 1 項目：F-18 `(77004003, SCT, "^18^Fluorine")`、FDG `(35321007, SCT, "Fluorodeoxyglucose F^18^")`、投与の日時（撮影の 60 分前。Radiopharmaceutical Start DateTime (0018,1078) と、古い表示系向けに Type 3 の Radiopharmaceutical Start Time (0018,1072)）、総量 370 MBq、半減期 6586.2 s、陽電子率 0.97 |
| Patient Orientation Code Sequence・Patient Gantry Relationship Code Sequence (0054,0410・0414) | 2 | 空 |
| Image Type (0008,0008) | 1 | `ORIGINAL\PRIMARY` |
| Samples per Pixel / Photometric Interpretation | 1 | `1` / `MONOCHROME2` |
| Bits Allocated / Bits Stored / High Bit | 1 | `16` / `16` / `15`。Pixel Representation は `0` |
| Rescale Intercept / Slope (0028,1052・1053) | 1 | `0` / `1`（PET では Intercept は常に 0。C.8.9.4） |
| Frame Reference Time (0054,1300) | 1 | `60000`（フレームの中ほど。C.8.9.4.1.5 の例 1） |
| Image Index (0054,1330) | 1 | シリーズの中の画像の番号（1 始まり） |
| Acquisition Date / Time (0008,0022・0032) | 2 | 検査の日時 |
| Actual Frame Duration (0018,1242) | 2 | 120000 ms |
| Decay Factor (0054,1321) | 1C | Frame Reference Time から撮影の開始（Series の日時）までの減衰 `2^(60 / 半減期)`（約 1.0063） |

- Decay Correction が `START` なので、画素は撮影の開始の時刻に補正した値で、Decay
  Factor はフレームの中の減衰の分だけ。補正した時刻は Decay Factor・Frame Reference
  Time・半減期・Series の日時から求まる（C.8.9.1.1.5）。投与の時刻への補正（`ADMIN`）
  ではないので、投与から撮影までの 60 分の減衰は入れない
- 行列は 128 × 128、視野は 700 mm（Pixel Spacing は 700 ÷ 128）。ジョブの画素の大きさ
  には従わない。画素の値は 0〜32767：`ct_realistic` は負でない値をそのまま、
  `simple_text` は 0〜32767 に伸ばす
- Image Position (Patient)・Image Orientation (Patient)・Slice Location・Slice
  Thickness は CT の軸位と同じ軸（z）に、スライス厚ずつ進める。PET のスライス厚は
  3.27 mm（ルーチン）
- PET の再構成（`pet_ac`・`pet_nac`）は別のシリーズ（C.8.9.1 の Note）。Series
  Description と Protocol Name はルーチンの値

## 6. マルチスライスの空間座標

### 6.1 計算の規則

シリーズの i 枚目（0 始まり）の値は `SpatialCalculator`
（`app/core/dicom_writer.py`）が計算する。`start_z`・`slice_spacing`・
`slice_thickness` は Job の `series_list` の値（既定は 0.0・5.0・5.0 mm）。

| Tag | Attribute Name | Type | 値 |
|-----|----------------|------|----|
| (0020,0013) | Instance Number | 2 | i + 1 |
| (0020,0032) | Image Position (Patient) | 1 | `[0, 0, z]`。z = `start_z` + i × `slice_spacing` |
| (0020,0037) | Image Orientation (Patient) | 1 | `[1, 0, 0, 0, 1, 0]`（固定） |
| (0020,1041) | Slice Location | 3 | z |
| (0018,0050) | Slice Thickness | 2 | `slice_thickness`（シリーズで共通） |
| (0028,0030) | Pixel Spacing | 1 | `[0.5, 0.5]`（固定） |

Type は PS3.3 C.7.6.1（General Image）と C.7.6.2（Image Plane）による。
モダリティテンプレートの `spatial` の節は読まない。

例：20 枚、厚さ 5 mm、間隔 5 mm、開始 z = 0 のとき

| i | Instance Number | Image Position (Patient) | Slice Location |
|---|-----------------|--------------------------|----------------|
| 0 | 1 | `[0, 0, 0]` | 0 |
| 1 | 2 | `[0, 0, 5]` | 5 |
| 19 | 20 | `[0, 0, 95]` | 95 |

### 6.2 DS の書き方

DS（Decimal String）は 16 バイトまで（PS3.5 6.2 の表 6.2-1）。
`str(float)` は浮動小数点の誤差で 16 文字を超える（間隔 0.1 の 4 枚目は
`0.30000000000000004`、身長 165.7 cm は `1.6569999999999998` m）。
DTG が数値から作成する DS（Image Position (Patient)・Image Orientation
(Patient)・Slice Location・Slice Thickness・Pixel Spacing・Patient's
Weight・Patient's Size）は、有効 12 桁で丸めてから
`pydicom.valuerep.format_number_as_ds` で 16 文字以内にする
（`app/core/generator.py` の `format_ds`）。上の例は `0.3`・`1.657` になる。
小さい値は 0 にせず、指数表記で残す（`1e-07`。DS は指数表記を許す）。

## 7. 文字コード

### 7.1 Specific Character Set (0008,0005)

値は次の順に決め、後のものが前のものを上書きする。

1. Job の `character_set.specific_character_set`（既定
   `ISO 2022 IR 6\ISO 2022 IR 87`）
2. 病院テンプレートの `overrides.character_set.specific_character_set`
3. 装置プロファイルの `character_set.default`（病院テンプレートが 2 を
   書いていないときだけ。spec/13）

- `\` で区切った値は複数の値として書く（PS3.3 C.12.1.1.2）
- 値が空なら (0008,0005) を書かない。このとき患者名に ASCII 以外の文字が
  あれば `DICOMBuildError` で停止する（PS3.3 C.12.1 の Type 1C）
- 病院テンプレートが値に `null` を書いたときは、患者名に ASCII 以外の文字が
  あれば `ISO 2022 IR 6\ISO 2022 IR 87` を書き、無ければ書かない
- 予約からの撮影では、Specific Character Set と患者の値を予約の値で
  上書きする（spec/12 の 6 章）

### 7.2 PN の構成

PN（Person Name）は英字・漢字・かなの 3 つのコンポーネントグループを `=` で
つなぐ（PS3.5 6.2.1）。Job の `patient.patient_name` の `alphabetic`・
`ideographic`・`phonetic` をこの順に並べる。

```text
YAMADA^TARO=山田^太郎=ヤマダ^タロウ
```

- 英字のコンポーネントグループは常に書く（モダリティエミュレーターの身元不明の患者は
  英字を空にし、先頭を `=` にする。[12a](12a_web_screens_and_cli.md) の 10.5）
- 漢字は `use_ideographic`、かなは `use_phonetic` が `true` で、値があるときだけ
  書く。どちらも Job の `character_set` の値を、病院テンプレートの
  `overrides.patient_module.patient_name` が上書きする。
  `use_alphabetic` は読まない
- 末尾の空のコンポーネントグループは削除する。途中の空は残す
  （漢字が無くかながある例：`YAMADA^TARO==ヤマダ^タロウ`）

### 7.3 病院テンプレート

`templates/hospital/` の 2 つのテンプレートの出力は次のとおり。

| テンプレート | Specific Character Set | Patient's Name |
|--------------|------------------------|----------------|
| `hospital_a` | `ISO 2022 IR 6\ISO 2022 IR 87` | `YAMADA^TARO=山田^太郎=ヤマダ^タロウ` |
| `hospital_b` | （書かない） | `YAMADA^TARO` |

`ISO 2022 IR 6\ISO 2022 IR 87`（`hospital_a` と、Job の `specific_character_set` の既定）の
画像は、Orthanc 1.13.0 が漢字・かなを読み崩す。Orthanc は最初の値が空でない複数の値を、
最初の値だけで全体を読むため。Orthanc へ送る Job では、`\ISO 2022 IR 87`（値 1 が空）か
`ISO_IR 192` にする（確かめた結果は [spec/12](12_modality_emulator.md) の 14.4）。

### 7.4 表現できない文字

Specific Character Set は、デフォルトの文字セット（ASCII）に無い文字を使う
ときに必須（PS3.3 C.12.1 の Type 1C、PS3.5 6.1）。宣言した文字コードで
表現できない文字を書き出すと、pydicom は `?` に置き換えるか、宣言に無い
バイト列のまま書き出す。DTG は、画像を 1 枚書き出す前にその画像のすべての
文字列の属性を検証し、表現できない文字があればその画像を書き出さずに停止する
（それより前に書き出した画像は残る。
[ADR-0018](../decisions/0018-stop-on-unrepresentable-characters.md)）。
予約からの撮影は `WorklistMappingError`（spec/12 の 7.2）、
Job からの作成は `DICOMValidationError`（どちらも CLI の終了コード 4。
spec/04）。Job からの作成のエラーメッセージとログには、属性の名前と文字コード
だけを出し、表現できない文字そのもの（氏名の一部など）は出さない。
例：文字コードが空の病院テンプレート（`hospital_b`）で、Job の紹介医名や
検査の説明に漢字・`é` があれば停止する。

## 8. Patient's Age (0010,1010)

Patient's Age は Job の `patient.age` を使わず、`birth_date` と
`study_date` から日本の法律の基準で算出する
（[ADR-0008](../decisions/0008-patient-age-derived-from-dates.md)）。

### 8.1 法的根拠

- **年齢計算ニ関スル法律**（明治 35 年法律第 50 号）：出生の日から起算する
- **民法 143 条**：期間を年で定めたときは暦に従って計算する。応当日が無いときは
  その月の末日に満了する

### 8.2 算出の規則

N 歳に達する日（加齢日）は、誕生日の前日の N 年後の同じ月日とする。その日が
存在しないとき（前日が 2 月 29 日で、N 年後が閏年でない）は 2 月 28 日とする。
年齢は、加齢日が検査日以前である最大の N。

### 8.3 2 月 29 日生まれの例

| 生年月日 | 検査日 | 値 | 理由 |
|----------|--------|----|------|
| 2000-02-29 | 2025-02-27 | `024Y` | 加齢日（2/28）の前日 |
| 2000-02-29 | 2025-02-28 | `025Y` | 閏年でない年の加齢日 |
| 2000-02-29 | 2024-02-28 | `024Y` | 閏年の加齢日 |

### 8.4 制約

- `study_date` は `birth_date` 以上でなければならない（Job の検証のエラー。
  spec/07）
- 値は AS の形式 `nnnY`（PS3.5 6.2）。0〜999 の範囲の外は `DICOMBuildError`

## 9. Transfer Syntax

### 9.1 作成する Transfer Syntax

| Transfer Syntax | UID | VR | Endian |
|-----------------|-----|----|--------|
| Implicit VR Little Endian（既定） | 1.2.840.10008.1.2 | Implicit | Little |
| Explicit VR Little Endian | 1.2.840.10008.1.2.1 | Explicit | Little |

Job の `transfer_syntax.uid` で選ぶ。符号化の方法は UID から決まり、Job の
`transfer_syntax` の `name`・`is_implicit_vr`・`is_little_endian` は使わない。
この 2 つが `app/core/generator.py` の `DICOMBuilder` が受け付ける Transfer
Syntax で、ほかの UID は `DICOMBuildError` になる。

### 9.2 Explicit VR Big Endian

Explicit VR Big Endian（1.2.840.10008.1.2.2）は規格で廃止された形式
（PS3.5 A.3）なので作成しない
（[ADR-0015](../decisions/0015-no-explicit-vr-big-endian.md)）。Job で
指定すると、出力フォルダを作成する前に停止する。

- 装置プロファイルを選択していれば、先にプロファイルと合うかを検証する。
  プロファイルが Big Endian を持たなければ `ProfileMismatchError`
  （CLI の終了コード 2）
- その検証を通過した Big Endian の指定は `DICOMValidationError`（終了コード 4）
- 装置プロファイルの最初の Transfer Syntax が Big Endian で、それを使う
  経路（`quick --profile` とモダリティエミュレーターの撮影で、プロファイルから
  Transfer Syntax を決めるとき）は `ProfileMismatchError`（終了コード 2）

異常のデータの定義（spec/02）にも含まれないので、異常のデータのレベルに関わらず
作成しない（1.1 の「通常の経路と異常のデータの経路」）。

## 10. 参考資料

1. **DICOM Standard**：<https://www.dicomstandard.org/>
2. **pydicom**：<https://pydicom.github.io/>
3. **IHE Japan**：<https://www.ihe-j.org/>（OID の取得の情報）
4. **ITU-T X.667（ISO/IEC 9834-8）**：UUID から 2.25 の OID を作る規則
   （PS3.5 B.2 が参照する）
5. **装置のコンフォーマンスステートメント**（DICOM PS3.2 Annex N の形式）：
   再現する装置ごとに参照する。どの文書のどの版から転記したかは、外部の
   配置場所のプロファイルの `source` に書く（spec/13）
