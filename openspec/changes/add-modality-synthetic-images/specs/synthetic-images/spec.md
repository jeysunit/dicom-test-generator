# Spec Delta

## ADDED Requirements

### Requirement: 図形の方式はスライスの位置で画素を変える

DTG は、画素の方式 `phantom` を選んだとき、各画素の患者座標で3次元の図形を評価して
画素を作らなければならない（SHALL）。図形の中心と半径は、1回の撮影（同じ Frame of
Reference UID の画像の組）で一度だけ患者座標で決め、全シリーズで同じものを使う。
軸位・冠状断・矢状断の画像は同じ図形の断面になる。`phantom` のときは、冠状断と
矢状断の画像を、軸位の範囲を覆う位置に置く（Image Position (Patient) の z を軸位の
範囲の上端にする）。どの画像にも、シリーズの中の番号に合わせて角度を変えた
位置の目印を描く。目印は3次元の図形に含めない。

#### Scenario: 軸位のシリーズで円の大きさが変わる

- **WHEN** `phantom` で、軸位 30 枚のシリーズを作る
- **THEN** 図形の画素の数（目印と帯を除く）は、1枚目から 15 枚目まで増え続け、15 枚目と 16 枚目でいちばん多く、16 枚目から 30 枚目まで減り続ける（隣どうしで同じ数になってもよいが、逆向きには変わらない）

#### Scenario: 中央から同じ距離の2枚

- **WHEN** `phantom` の軸位 30 枚のうち、1枚目と 30 枚目、15 枚目と 16 枚目を比べる
- **THEN** どちらの組も、位置の目印の位置が違う

#### Scenario: 断面の間で同じ図形

- **WHEN** 同じ撮影で、スライス厚と枚数の違う軸位2つと冠状断・矢状断を `phantom` で作り、それらの画像が交わる線の上で、図形の内側・境界の近く・外側の点を選ぶ
- **THEN** どの点も、交わるすべての画像で区分が同じ（目印と帯の画素は比べない）

#### Scenario: 冠状断に図形が写る

- **WHEN** 胸部 単純のルーチンを `phantom` で撮る
- **THEN** COR 3mm の中央の画像に、図形の区分の画素がある

### Requirement: 図形の方式の画像は明らかに偽物と分かる

DTG は、`phantom` の画像を、楕円体・楕円柱・円柱・直方体とその殻の組み合わせだけで
描き、区分ごとに一定の値にしなければならない（SHALL）。ノイズ・ぼかし・臓器や骨の
輪郭を描いてはならない（SHALL NOT）。どの画像にも、上端の帯に `TEST / SYNTHETIC`・
患者 ID・検査日・シリーズ番号・何枚目か・位置（投影の画像は方向）を、画素の値の
最小と最大だけで焼き込む。Burned In Annotation (0028,0301) は `YES`、Recognizable Visual Features
(0028,0302) は `NO`、Image Comments (0020,4000) は
`SYNTHETIC TEST IMAGE - NOT FOR DIAGNOSIS` にする（PS3.3 C.7.6.1）。

#### Scenario: 帯の外の値の種類

- **WHEN** `phantom` で、基本の図形（回転楕円体と目印）の画像を作る
- **THEN** 帯の外の画素の値は、背景・図形・目印の 3 種類以下

#### Scenario: 位置決めの画像にも帯がある

- **WHEN** `phantom` で、CT の胸部 単純のルーチンを撮る
- **THEN** 位置決めを含む全画像の上端の帯に、最大の値の画素がある

#### Scenario: 焼き込みの属性

- **WHEN** `phantom` で画像を作る
- **THEN** Burned In Annotation は `YES`、Recognizable Visual Features は `NO` で、Image Comments に `SYNTHETIC TEST IMAGE - NOT FOR DIAGNOSIS` が入る

#### Scenario: 描けない字

- **WHEN** 患者 ID に ASCII 以外の字がある予約を `phantom` で撮る
- **THEN** その字は `?` で焼き込まれ、撮影は止まらない

### Requirement: 図形の方式は選んだときだけ使う

DTG は、画素の方式の既定を `ct_realistic` のままにしなければならない（SHALL）。
`phantom` は、Job の `pixel_spec.mode`、CLI の `--pixel-mode`、設定の
`modality.default_pixel_mode` のどれかで選んだときだけ使う。`phantom` を選ばない
画像は、画素も属性も今と同じにする。線量の画面と線量の報告の SR は、方式によらず
今のまま作る。

#### Scenario: 何も選ばない撮影

- **WHEN** 設定の `default_pixel_mode` を変えずに、`--pixel-mode` を付けずに `exam` を実行する
- **THEN** 画像の画素と属性は、この変更の前と同じ（Burned In Annotation は無い）

#### Scenario: CLI で選ぶ

- **WHEN** `quick --pixel-mode phantom` を実行する
- **THEN** 図形の画像が作られる

### Requirement: CR と DX の画像を作れる

DTG は、モダリティが CR のシリーズを CR Image Storage（1.2.840.10008.5.1.4.1.1.1）、
DX のシリーズを Digital X-Ray Image Storage - For Presentation
（1.2.840.10008.5.1.4.1.1.1.1）で作らなければならない（SHALL）。CR は方向ごとに
1シリーズにし、View Position (0018,5101) と Body Part Examined (0018,0015) を
シリーズの値にする（PS3.3 C.8.1.1）。DX は1シリーズに全部の方向を入れ、
Presentation Intent Type (0008,0068) を `FOR PRESENTATION` にし、DX Image Module
の Type 1 の属性（Image Type の Value 3 は長さ 0、Pixel Intensity Relationship・
Sign、Rescale の 0・1・`US`、Presentation LUT Shape、Lossy Image Compression
`00`、Burned In Annotation）、Image Laterality、Anatomic Region Sequence、Imager
Pixel Spacing を入れる（PS3.3 C.8.11）。どちらも Frame of Reference と Image Plane
を持たず、Patient Orientation (0020,0020) を入れる。DX は Modality LUT を持たない。

#### Scenario: CR の胸部

- **WHEN** CR の胸部の予約を撮る
- **THEN** テンプレート `cr_generic` が選ばれ、View Position が `PA` と `LL` の2つのシリーズ（各1枚）ができ、どちらも Frame of Reference UID を持たない

#### Scenario: DX の胸部

- **WHEN** DX の胸部の予約を撮る
- **THEN** 1つのシリーズに2枚ができ、Presentation Intent Type は `FOR PRESENTATION`、Image Type は `ORIGINAL\PRIMARY\`（Value 3 は長さ 0）、Image Laterality は `U`、Anatomic Region Sequence は SCT 816094009 になる

#### Scenario: 図形の方式でない DX

- **WHEN** `ct_realistic` で DX の画像を作る
- **THEN** Burned In Annotation は `NO` になる（DX Image Module で Type 1）

#### Scenario: MONOCHROME1 のテンプレート

- **WHEN** Photometric Interpretation を `MONOCHROME1` にしたテンプレートで DX を撮る
- **THEN** 画素は `MONOCHROME2` の値を上限から引いた値になり、Presentation LUT Shape は `INVERSE`、Pixel Intensity Relationship Sign は `+1` になる

### Requirement: 図形の方式は部位と撮像で図形と値を変える

DTG は、ルーチンの `phantom`（`head`・`chest`・`trunk`・`abdomen`・`spine`・`limb`）で
図形の組を選び、MR はシリーズの `weighting`、CT の造影のシリーズは `phase` で区分の
値を変えなければならない（SHALL）。`phantom` を書いていないルーチンと手で入れた
シリーズは、基本の図形（回転楕円体と目印）にする。値は design.md の表の架空の値にする。

#### Scenario: 頭部の CT

- **WHEN** CT の頭部 単純のルーチンを `phantom` で撮る
- **THEN** 軸位の画像に、HU 1000 の楕円の輪と、その中の HU 40 の楕円がある

#### Scenario: 腰椎で骨とすきまが交互になる

- **WHEN** CT の腰椎のルーチンの軸位を `phantom` で撮る
- **THEN** z が進むにつれ、背側の骨の区分がある画像と無い画像が交互に現れる

#### Scenario: MR の T1 と T2

- **WHEN** MR の頭部のルーチンを `phantom` で撮る
- **THEN** 液の区分の値は、T2 AX の画像のほうが T1 SAG の画像より大きい

#### Scenario: 造影の相

- **WHEN** CT の肝臓 ダイナミックのルーチンを `phantom` で撮る
- **THEN** 血管の区分は、AX 5mm で HU 40、Arterial 3mm で HU 300 になる
