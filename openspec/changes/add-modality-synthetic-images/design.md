# Design

## 今の姿

2026-10-27 の `main`（6f8cbfb）で確かめた。

| 項目 | 今の姿 | 場所 |
|------|--------|------|
| 画像を作れるモダリティ | CT（CT Image Storage）・MR（MR Image Storage）・PT（PET Image Storage）。線量の画面は Secondary Capture、線量の報告は X-Ray Radiation Dose SR | `app/core/generator.py`、spec/06 の 5 章 |
| モダリティのテンプレート | `ct_generic`・`mr_generic`・`petct_generic` | `templates/modality/` |
| 例の装置のプロファイル | `dtg_synthetic_ct`・`dtg_synthetic_mr`・`dtg_synthetic_petct` | `profiles/examples/` |
| ルーチン | CT 7・MR 4・PT 2・CR 6・DX 6・US 1。CR・DX・US は並びと枚数だけで、画像を作る処理が無い（`routine_series_configs` が「CR の画像はまだ作れません」で断る） | `templates/routine/`、`app/core/routine.py` |
| CT のシリーズの種類 | 位置決め・軸位・冠状断・矢状断・線量の画面（ADR-0025） | `app/core/series_layout.py` |
| MR のシリーズの種類 | 位置決め（三方向）・撮像・計算で作った画像。断面・シーケンス・2D/3D を持つ（ADR-0030） | 同上 |
| 画素の方式 | `simple_text`（SOP Instance UID の文字）と `ct_realistic`（`gradient`・`circle`・`noise`）。撮影の既定は `ct_realistic` の `gradient` | `app/core/pixel_generator.py`、`app/modality/config.py` |
| 画素と位置の関係 | 無い。1つのシリーズの全画像が同じ絵になる（`noise` は画像ごとに違うが、位置とは関係しない） | `app/services/study_generator.py` の `_generate_pixel_data` |
| 焼き込みの属性 | Burned In Annotation (0028,0301) と Recognizable Visual Features (0028,0302) を書かない | `app/core/generator.py` |
| 規格の確かめ | pytest で属性の Type と値を確かめる（`tests/core/test_ct_image_conformance.py` など）。dciodvfy などの外部の検査器は使っていない | `tests/` |

足りないものは次の4つである。

1. CR・DX の画像を作る処理（IOD・テンプレート・装置のプロファイル）
2. スライスの位置で変わる画素
3. 検査の部位で変わる画素
4. 偽物と分かる印（焼き込みと属性）

## 調べたこと

規格は DICOM PS3.3・PS3.4・PS3.16 の 2026d 版を、2026-10-27 に Defuddle で本文を
取り出して読んだ。番号は末尾の「出典」の番号。

### CR Image IOD（PS3.3 A.2）

- 必須のモジュールは Patient・General Study・General Series・CR Series・General
  Equipment・General Acquisition・General Image・Image Pixel・CR Image・SOP
  Common（Table A.2-1。出典 1）。Frame of Reference と Image Plane のモジュールは
  IOD に無い
- CR Series Module：Body Part Examined (0018,0015) と View Position (0018,5101) が
  Type 2。View Position はシリーズの値なので、方向の違う画像は別のシリーズになる
  （C.8.1.1。出典 3）
- CR Image Module：Photometric Interpretation は Type 1 で `MONOCHROME1` か
  `MONOCHROME2`。ほかの属性（KVP・Imager Pixel Spacing など）は Type 3（C.8.1.2。
  出典 3）
- General Image Module：Patient Orientation (0020,0020) は、Image Orientation
  (Patient) を要しない画像では必須（Type 2C。C.7.6.1。出典 4）。CR は Image Plane を
  持たないので必須になる

### DX Image IOD（PS3.3 A.26）

- 必須のモジュールは、CR と共通のものに加えて DX Series・DX Anatomy Imaged・DX
  Image・DX Detector・Acquisition Context。Presentation Intent Type が `FOR
  PRESENTATION` なら VOI LUT のモジュールも必須（Table A.26-1。出典 2）
- 1枚の画像は1回の X 線の照射の結果でなければならない（A.26.1。出典 2）
- DX Series Module：Modality は `DX`、Presentation Intent Type (0008,0068) は Type 1
  で `FOR PRESENTATION` か `FOR PROCESSING`。シリーズの全画像が同じ値になる
  （C.8.11.1。出典 5）。この Module の注は、View Position をシリーズの値にした CR の
  決まりが「PA と側面の胸部を1つのシリーズにできない」不便を生んだので、DX では
  画像ごとの値にしたと書く
- DX Anatomy Imaged Module：Image Laterality (0020,0062) は Type 1 で `R`・`L`・`U`・
  `B`。Anatomic Region Sequence は General Anatomy Required Macro で Type 1、
  CID 4009（中身は CID 4031）から選ぶ（C.8.11.2。出典 6）
- DX Image Module（C.8.11.3。出典 7）：
  - Image Type の Value 3 は「存在し、長さ 0」
  - Bits Allocated は 8 か 16、Bits Stored は 6〜16、Pixel Representation は 0
  - Pixel Intensity Relationship (0028,1040) は `LIN` か `LOG`、Sign (0028,1041) は
    `+1` か `-1`
  - Rescale Intercept は 0、Slope は 1、Rescale Type は `US`。Modality LUT の
    モジュールを入れてはならない
  - Presentation LUT Shape (2050,0020) は、`MONOCHROME2` なら `IDENTITY`、
    `MONOCHROME1` なら `INVERSE`
  - Lossy Image Compression (0028,2110) と Burned In Annotation (0028,0301) は Type 1
  - Patient Orientation は Type 1C（View Code Sequence が標本でなければ必須）
  - `FOR PRESENTATION` なら Window Center・Width か VOI LUT Sequence が必須
- DX Detector Module：Detector Type (0018,7004) は Type 2、Imager Pixel Spacing
  (0018,1164) は Type 1（C.8.11.4。出典 8）
- DX Positioning Module（任意）：View Position と View Code Sequence は Type 3。
  View Code Sequence は「入れることを強く勧める」（C.8.11.5。出典 9）
- SOP Class：CR Image Storage は `1.2.840.10008.5.1.4.1.1.1`、DX For Presentation は
  `1.2.840.10008.5.1.4.1.1.1.1`、For Processing は `1.2.840.10008.5.1.4.1.1.1.1.1`
  （PS3.4 B.5。出典 10）

### 焼き込みの属性（PS3.3 C.7.6.1）

General Image Module の Burned In Annotation は、`YES` を「患者と撮影日を識別できる
だけの文字が画像に焼き込まれている」と定める。Type 3 で、無ければ「焼き込みが
あるかどうか分からない」。Recognizable Visual Features (0028,0302) は「画像（か
画像の組から作った再構成）で患者を識別できる見た目の特徴があるか」で、同じく
Type 3（出典 4）。DX Image Module では Burned In Annotation が Type 1 になる（出典 7）。

### コード（PS3.16）

| 部位 | Body Part Examined | Anatomic Region Sequence（SCT） |
|------|--------------------|---------------------------------|
| 胸部 | `CHEST` | 816094009 Chest |
| 腹部 | `ABDOMEN` | 818981001 Abdomen |
| 腰椎 | `LSPINE` | 122496007 Lumbar spine |
| 頸椎 | `CSPINE` | 122494005 Cervical spine |
| 膝 | `KNEE` | 72696002 Knee |
| 手 | `HAND` | 85562004 Hand |

Body Part Examined の語は PS3.16 Annex L（前の change の出典 40）、コードは CID 4031
（出典 11）。View Code Sequence は CID 4010 の PA 272479007、AP 399348003、
左側面 399173006、右側面 399198007 を使う（出典 12）。斜位（`RLO`・`LLO`）と
側臥位（`RLD`・`LLD`）は View Position だけを書き、View Code Sequence は入れない
（コードを確かめていないため）。

## 検査ごとのシリーズの構成

依頼者が挙げた例（頭部 CT 単純、胸部 CT、腹部の造影の多相、MR 頭部、胸部 X 線の
PA と側面、DX の四肢）は、どれも今のルーチンにある。シリーズの並びと枚数は
前の change（`archive/2026-10-24-add-exam-routine-templates/design.md`）で公開の
資料から決めたもので、どれも代表例である。施設で違う部分は、施設のルーチンの
YAML を足して変える。この change ではルーチンを足さず、各ルーチンに図形の部位
（`phantom`）を書き足す。

| モダリティ | 検査（ルーチン） | シリーズの並び（枚数） | 図形 |
|------------|------------------|------------------------|------|
| CT | 頭部 単純 | 位置決め 側面(1)／AX 5mm(30)／AX BONE 2.5mm(60)／線量の画面(1) | `head` |
| CT | 胸部 単純（既定） | 位置決め 正面(1)／縦隔 5mm(60)／肺野 5mm(60)／肺野 1mm(300)／COR 3mm(83)／線量の画面(1) | `chest` |
| CT | 胸腹部骨盤 造影 | 位置決め(1)／Ax Chest 2mm +C(150)／Ax A/P 3mm +C(133)／Cor 3mm +C(83)／Sag 3mm +C(116)／線量の画面(1) | `trunk` |
| CT | 腹部骨盤 単純＋造影 | 位置決め(1)／AX 5mm(80)／AX 5mm +C(80)／COR 3mm +C(83)／SAG 3mm +C(116)／線量の画面(1) | `abdomen` |
| CT | 肝臓 ダイナミック | 位置決め(1)／AX 5mm(50)／動脈相 3mm(83)／門脈相 3mm(83)／平衡相 3mm(83)／COR 門脈相 3mm(83)／線量の画面(1) | `abdomen` |
| CT | 冠動脈 CTA | 位置決め(1)／石灰化スコア 3mm(40)／CTA 0.5mm +C(280)／線量の画面(1) | `chest` |
| CT | 腰椎 | 位置決め 2方向(2)／AX・SAG・COR の BONE と SOFT（75・30・30・75・30）／線量の画面(1) | `spine` |
| MR | 頭部（既定） | ローカライザー 三方向(15)／DWI b1000(25)／ADC(25)／T2*(25)／T1 SAG(25)／T2 AX(25)／FLAIR(25)／TOF MRA(116) | `head` |
| MR | 腰椎 | ローカライザー(15)／T1 SAG(18)／T2 SAG(18)／T2 AX(45) | `spine` |
| MR | 膝 | ローカライザー(15)／PD FS SAG(30)／T2 FS COR(30)／PD FS AX(30)／T1 COR(30) | `limb` |
| MR | 肩 | ローカライザー(15)／T2 FS AX(24)／T2 FS COR(24)／T1 COR(24)／T1 SAG(24) | `limb` |
| CR | 胸部（既定） | PA(1)／側面(1)。方向ごとに1シリーズ | `chest` |
| CR | 腹部 | 臥位 AP(1)／立位 PA(1) | `abdomen` |
| CR | 腰椎・頸椎 | AP と側面（頸椎は開口位の AP を足す） | `spine` |
| CR | 膝・手 | 膝は AP と側面、手は PA・斜位・側面 | `limb` |
| DX | 胸部（既定） | 1シリーズに PA と側面(2) | `chest` |
| DX | 腹部・腰椎・頸椎・膝・手 | CR と同じ方向を1シリーズにまとめる | CR と同じ |

MR の各シリーズには強調（`weighting`）を書き足す。頭部は DWI・ADC・T2STAR・T1・
T2・FLAIR・MRA、腰椎は T1・T2、膝は PD・T2・PD・T1、肩は T2・T2・T1・T1 にする。
CT の造影のシリーズには相（`phase`）を書き足す。肝臓 ダイナミックは動脈相・門脈相・
平衡相、冠動脈 CTA の CTA は動脈相にする。`phase` の無い造影のシリーズは門脈相の
値で描く。

US はこの change の範囲に入れない（依頼の範囲は CT・MR・CR/DX）。

## 基本の図形：位置で変わる図形（`phantom`）

### 図形の置き方

図形は、画像の患者座標（Image Position (Patient)・Image Orientation (Patient)・
Pixel Spacing から計算する、各画素の中心の x・y・z）で評価する。図形の中心と
半径は、1回の撮影（同じ Frame of Reference UID の画像の組）で一度だけ患者座標で
決め、その撮影の全シリーズで同じものを使う。シリーズごとに決め直すと、断面や
枚数を変えただけで別の図形になり、MPR や位置合わせの試験の基準にならないため。

基本の図形は、回転楕円体1つと位置の目印である。

- 回転楕円体の中心の x・y は、軸位の視野（列・行の数 × 画素間隔）の中央に置く。
  z は、その撮影の軸位のシリーズのうち位置の範囲がいちばん長いものの範囲の中央に
  置く。軸位が無い撮影（MR の矢状断だけなど）は、最初の断層のシリーズの範囲で
  決める
- x・y の半径は視野の 0.4 倍、z の半径はその範囲の 0.55 倍にする。範囲の中央の
  画像で円がいちばん大きく、両端に向かって小さくなる。両端の画像でも円は消えない
- 位置の目印は3次元の図形ではなく、画像ごとに描く印である。1辺が視野の 0.04 倍の
  正方形で、画像の中心から視野の 0.3 倍の円の上に置く。角度はシリーズの中の番号
  k（0 始まり）と画像の数 n から 360° × k / n にする。回転楕円体は中央に対して
  対称なので、中央から同じ距離の2枚は円の大きさが同じになる。目印の角度が違うので、
  その2枚も見分けられる

今の冠状断・矢状断の画像の位置（spec/06 の 5.1）は、軸位と同じ範囲を覆わない。
冠状断の Image Position (Patient) は `[0, y, 0]` で、列は −z の向きに進むので、
画像は z が 0 以下の範囲を写す。軸位は z が `start_z`（既定 0）から +z に進むので、
冠状断と軸位はほとんど交わらず、冠状断に図形がほぼ写らない。そこで、`phantom` の
ときだけ、冠状断と矢状断の Image Position (Patient) の z を、その撮影の軸位の範囲の
上端にする（推奨。proposal の「依頼者が決めること」の 8）。ほかの方式の位置は
今のままにする。

位置決め・CR・DX のような投影の画像は、位置が変わらないので、基本の図形では体の楕円
1つを描き、方向と何枚目かを焼き込みの文字で示す。

### 値

区分ごとに一定の値にする。

| 区分 | CT（HU。画素は HU + 1024） | MR（Bits Stored の上限に対する割合） | CR・DX（同じ割合。`MONOCHROME2`） |
|------|---------------------------|---------------------------------------|----------------------------------|
| 背景（空気） | −1000 | 0 | 0.05 |
| 図形（軟部） | 40 | 0.40 | 0.35 |
| 位置の目印（骨） | 1000（12 ビットの上限 1023 以下） | 0.90 | 0.80 |

Rescale・Window の値は、今の CT・MR の値のままにする（spec/06 の 4.2・5.2）。

### 焼き込みの文字

画像の上端に、最小の値の帯を敷き、最大の値で次の3行を描く。

```text
TEST / SYNTHETIC  ID P000001  20261027
SE 3  IM 12/60
Z +55.0 mm
```

- 3行目は、軸位は `Z`、冠状断は `Y`、矢状断は `X` と位置（mm）。投影の画像は
  `VIEW PA` のように方向を描く
- 文字は Pillow の既定のフォントで描き、画像の幅 256 画素ごとに 1 倍ずつ、最近傍で
  拡大する。外部のフォントに頼らないので、Docker のイメージでも同じに描ける
- 描くのは ASCII の印字できる字だけで、ほかの字は `?` にする（患者 ID に全角の字が
  あるとき）
- 帯は Window の幅を変えても読めるように、画素の値の最小と最大だけで描く

### 属性

`phantom` の画像には次を書く。ほかの方式の画像には書かない（今と同じ）。DX の
Burned In Annotation は Type 1 なので、ほかの方式では `NO` を書く（PR 2）。

| 属性 | 値 |
|------|----|
| Burned In Annotation (0028,0301) | `YES` |
| Recognizable Visual Features (0028,0302) | `NO` |
| Image Comments (0020,4000) | `SYNTHETIC TEST IMAGE - NOT FOR DIAGNOSIS` |

### 選び方

- Job：`pixel_spec.mode: phantom`（`PixelSpecPhantom`。幅・高さは今と同じ範囲）
- CLI：`--pixel-mode phantom`（`quick` と `exam`）
- 設定：`modality.default_pixel_mode: phantom`
- 既定は今の `ct_realistic` のまま。線量の画面（Secondary Capture）と線量の報告の
  SR は、方式によらず今のまま作る

## 部位の図形

ルーチンの `phantom`（`head`・`chest`・`trunk`・`abdomen`・`spine`・`limb`）で図形を
選ぶ。書いていないルーチンと「手で入れる」のシリーズは、基本の図形にする。図形は
どれも楕円体・楕円柱・円柱・直方体と、その殻（輪）の組み合わせで、臓器や骨の輪郭は
描かない。

| 図形 | 3次元の組み合わせ（断層の画像） | 投影の画像（位置決め・CR・DX） |
|------|-------------------------------|--------------------------------|
| `head` | 楕円体の殻（骨、厚さ 6 mm）・その中の楕円体（軟部）・中央の小さい楕円体（液） | 楕円の輪（骨）と中（軟部） |
| `chest` | 体の楕円柱（軟部）・左右の楕円体2つ（肺）・中央の円柱（血管）・背側の円柱（骨） | 体の矩形・肺の楕円2つ・中央の縦長の矩形（軟部）。側面は肺の楕円1つ |
| `trunk` | 上半分は `chest`、下半分は `abdomen` | 同じく上下に分ける |
| `abdomen` | 体の楕円柱・大きい楕円体1つと小さい楕円体2つ（実質）・中央の円柱（血管）・背側の円柱（骨） | 体の矩形・中央の縦の棒（骨） |
| `spine` | 体の楕円柱・背側に並ぶ直方体の列（骨）。直方体の間に 5 mm のすきま（軟部） | 縦に並ぶ矩形の列（骨） |
| `limb` | 細い円柱（軟部）・同じ軸の2本の円柱（骨）。2本の間に 8 mm のすきま | 縦の棒2本（骨）とすきま |

`spine` は z が進むと骨とすきまが交互に現れ、`chest` は肺の楕円の大きさが変わる。
基本の図形の位置の目印と焼き込みの文字は、部位の図形でもそのまま描く。

### CT の値（HU。架空）

| 区分 | 単純 | 動脈相 | 門脈相 | 平衡相 |
|------|------|--------|--------|--------|
| 空気 | −1000 | ← | ← | ← |
| 肺 | −850 | ← | ← | ← |
| 液 | 5 | ← | ← | ← |
| 軟部 | 40 | ← | ← | ← |
| 実質 | 55 | 90 | 120 | 95 |
| 血管 | 40 | 300 | 180 | 110 |
| 骨 | 1000 | ← | ← | ← |

### MR の値（Bits Stored の上限に対する割合。架空）

| 区分 | T1 | T2 | PD | FLAIR | T2STAR | DWI | ADC | MRA |
|------|----|----|----|-------|--------|-----|-----|-----|
| 空気・肺 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 軟部 | 0.40 | 0.35 | 0.45 | 0.40 | 0.30 | 0.40 | 0.30 | 0.10 |
| 液 | 0.10 | 0.90 | 0.60 | 0.05 | 0.80 | 0.05 | 0.90 | 0.10 |
| 実質 | 0.45 | 0.25 | 0.40 | 0.30 | 0.25 | 0.35 | 0.25 | 0.10 |
| 血管 | 0.10 | 0.05 | 0.10 | 0.05 | 0.05 | 0.05 | 0.20 | 0.95 |
| 骨 | 0.60 | 0.30 | 0.50 | 0.35 | 0.10 | 0.10 | 0.10 | 0.05 |

ローカライザーは T1 の値にする。`weighting` を書いていないシリーズは、シーケンス
から決める（SE は T2、IR は FLAIR、GR は T2STAR、EP は DWI。計算で作った画像は ADC）。

### X 線の値（`MONOCHROME2` の割合）

空気 0.05、肺 0.15、軟部・液・血管 0.35、実質 0.40、骨 0.80。`MONOCHROME1` では、
上限からこの値を引いた値を書く（表示は同じになる）。

## 明らかに偽物と分かる決まり

`phantom` の画像は、次の4つを守る。どれも試験で確かめる。

1. 図形は楕円体・楕円柱・円柱・直方体と、その殻の組み合わせだけで描き、区分ごとに
   一定の値にする。ノイズ・ぼかし・縁の滑らかな変化・質感を足さない。帯の外の画素の
   値の種類は、その図形の区分の数以下になる
2. 臓器・骨の輪郭を写した形を描かない。部位は、位置と大きさの違う図形の組で表す
3. どの画像にも焼き込みの帯を描く（位置決め・CR・DX も含む）。帯は最小と最大の値
   だけで描き、窓の幅を変えても読める
4. Burned In Annotation `YES`、Recognizable Visual Features `NO`、Image Comments の
   文字を書く

## CR・DX の DICOM の値（PR 2）

| 属性 | CR | DX |
|------|----|----|
| SOP Class | CR Image Storage | Digital X-Ray Image Storage - For Presentation |
| Modality | `CR` | `DX` |
| シリーズ | 方向ごとに1シリーズ（View Position はシリーズの値） | ルーチンの1シリーズに全部の方向 |
| Presentation Intent Type | 無い | `FOR PRESENTATION` |
| Image Type | `ORIGINAL\PRIMARY` | `ORIGINAL\PRIMARY\`（Value 3 は長さ 0） |
| Body Part Examined | ルーチンの `body_part`（Type 2） | ルーチンの `body_part`（Type 3） |
| View Position | シリーズの方向（Type 2） | 画像ごとの方向（DX Positioning、Type 3） |
| View Code Sequence | 無い | PA・AP・左側面・右側面のときだけ CID 4010 のコード |
| Laterality / Image Laterality | 対になる部位だけ Laterality (0020,0060) にルーチンの `laterality`（`R`・`L` だけ。PS3.3 C.7.3.1）。対にならない部位には書かない | Image Laterality にルーチンの `laterality`（`R`・`L`・`B`）。対にならない部位は `U` |
| Anatomic Region Sequence | 入れる（任意） | 入れる（Type 1。上のコードの表） |
| Patient Orientation | 正面の方向（AP・PA・斜位・側臥位）は `L\F`、側面（LL・RL）は `P\F` | 同じ |
| Photometric Interpretation | テンプレートの値（既定 `MONOCHROME2`） | 同じ |
| Bits Allocated / Stored / Pixel Representation | 16 / 12 / 0 | 同じ |
| Rows × Columns | 1248 × 1024（固定） | 同じ |
| Imager Pixel Spacing | `0.342\0.342`（架空） | 同じ（Type 1） |
| Pixel Intensity Relationship / Sign | 無い | `LOG` / `MONOCHROME2` は `-1`、`MONOCHROME1` は `+1` |
| Rescale Intercept / Slope / Type | 無い | `0` / `1` / `US` |
| Presentation LUT Shape | 無い | `MONOCHROME2` は `IDENTITY`、`MONOCHROME1` は `INVERSE` |
| Window Center / Width | 上限の 1/2 / 上限 | 同じ（`FOR PRESENTATION` なので必須） |
| Lossy Image Compression | 書かない | `00` |
| Burned In Annotation | `phantom` は `YES`、ほかは書かない | `phantom` は `YES`、ほかは `NO`（Type 1） |
| Detector Type | 無い | 空（Type 2） |
| Acquisition Context Sequence | 無い | 空（Type 2） |
| Frame of Reference・Image Plane | 持たない（装置のプロファイルが足しても外す） | 持たない |

- Patient Orientation は、正面の画像を患者に向き合って見る向きで描くとした値で、
  代表例である。PS3.3 C.7.6.1.1.1 の定義（行は左から右、列は上から下の向き）に
  合わせて、実装の PR で図と照らして確かめる
- `simple_text` と `ct_realistic` でも CR・DX を作れる。`ct_realistic` の画素は、MR と
  同じく符号なしの範囲に収める
- 予約と緊急の患者は、ADR-0030 の決まり（予約のモダリティに合うテンプレートで撮る）
  で `cr_generic`・`dx_generic` を選ぶ

## 既定を変えないこと

- 設定・CLI・Job の画素の方式の既定は `ct_realistic`（`gradient`）のまま。`phantom`
  を選ばない画像は、画素も属性も今と同じになる。PR 1 の最初に、今の既定の撮影の
  画素と属性のハッシュを固定する試験を足し、変更の後も同じことを確かめる
- 冠状断・矢状断の位置を直すのは `phantom` のときだけで、ほかの方式の位置は今と同じ
- 今の CT・MR・PT の試験は、書き換えずに通す
- CR・DX のテンプレートは今は無いので、CR・DX の画像は新しく作れるようになるだけで、
  今の撮影の結果は変わらない。ただし、spec/06 の 5.2 は「CR・US などのテンプレートは
  画像を作る前に断る」と定める。CR・DX でこれを確かめる試験があれば、PR 2 で直す前に
  承認を得る（試験の書き換えに当たる）。US は今のまま断る

## 試験の計画

| PR | 試験 | 内容 |
|----|------|------|
| PR 1 | 既定の固定 | `ct_realistic` と `simple_text` の今の画素・属性のハッシュが変わらない（変更の前に書く） |
| PR 1 | 位置で変わる | 軸位 30 枚で、隣の画像の図形の画素の数が違い、中央の画像でいちばん多い。中央から同じ距離の2枚は、目印の位置が違う |
| PR 1 | 断面の間で同じ図形 | スライス厚と枚数の違う軸位2つと冠状断・矢状断が交わる線の上で、図形の内側・境界の近く・外側の点の区分がすべての画像で同じ。胸部 単純の COR の中央の画像に図形が写る。ほかの方式では冠状断の位置が今と同じ |
| PR 1 | 偽物の決まり | 帯の外の画素の値の種類が区分の数以下。帯に最大の値の画素がある。全画像（位置決めを含む）に帯がある |
| PR 1 | 属性 | `phantom` で Burned In Annotation `YES`・Recognizable Visual Features `NO`・Image Comments。ほかの方式では無い |
| PR 1 | 選び方 | Job・`quick --pixel-mode phantom`・`exam --pixel-mode phantom`・設定の既定で選べる。不正な方式は今と同じく断る |
| PR 2 | CR の IOD | Table A.2-1 の必須のモジュールの Type 1・2 の属性がある。Frame of Reference UID と Image Position (Patient) が無い。方向ごとに1シリーズ |
| PR 2 | DX の IOD | Table A.26-1 の必須のモジュールと上の表の値。Image Type の Value 3 が長さ 0、Modality LUT Sequence が無い |
| PR 2 | `MONOCHROME1` | 画素が反転し、Presentation LUT Shape が `INVERSE`、Sign が `+1` |
| PR 2 | 撮影 | CR・DX の予約で `cr_generic`・`dx_generic` が選ばれ、ルーチンの並びで撮れる。Storage SCP のスタブが受け取る（`tests/integration/`） |
| PR 2 | 部位と左右 | CR・DX × `R`・`L`・`B`・省略で、CR の `B`、対になる部位の省略、対にならない部位の `R` を読み込みで断る。DX の胸部は Image Laterality `U`、CR の膝は Laterality `R` |
| PR 3 | 部位の図形 | `head` の軸位で、骨の輪の内と外の値。`spine` で z が進むと骨とすきまが交互になる。`chest` の側面の投影は肺の楕円が1つ |
| PR 3 | MR の強調 | T1 と T2 で液の値の大小が入れ替わる。MRA で血管が最大 |
| PR 3 | CT の相 | 動脈相の血管の値が 300 HU、単純が 40 HU |

外部の検査器（dicom3tools の dciodvfy）は依存に入れない（`requirements.txt` を
変えない）。PR 2 で CR・DX の見本の画像を手元の dciodvfy で一度検査し、結果を PR の
本文に書くことを推奨する。CI には入れない。

## PR の分け方

| PR | 中身 | spec・ADR |
|----|------|-----------|
| 1 | 基本の図形（`phantom`）を CT・MR に入れる | 02 の 3 章、03、06 の 4 章、07 の 3.6、12a の CLI。ADR-0033 を採用にする |
| 2 | CR・DX の画像。`phantom` は基本の図形の投影の画像 | 06 に CR・DX の節、13 の 4.3、roadmap。ADR-0034 を採用にする |
| 3 | 部位の図形・MR の強調・CT の相。ルーチンに `phantom`・`weighting`・`phase` を書く | 03・06・ルーチンの形（exam-routines） |

PR 2 は PR 1 に依存する（焼き込みの帯を使う）。PR 3 は PR 1 と 2 の後に入れ、
最後にこの change を archive する。

## 確かめること（実装の PR で）

- 斜位と側臥位の View Code Sequence のコード（CID 4010 の中で確かめる）
- Patient Orientation の値と、ビューアの表示の向き
- Pillow の既定のフォントの大きさは版で違う（10.1 から FreeType のフォント）。
  試験では文字の形を比べず、帯の範囲に最大の値があることだけを確かめる

## 出典

本文を Defuddle で取り出して読んだ（2026-10-27）。

| # | 資料 | URL |
|---|------|-----|
| 1 | DICOM PS3.3 A.2.3 CR Image IOD Module Table | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_A.2.3.html> |
| 2 | DICOM PS3.3 A.26 Digital X-Ray Image IOD（A.26.1・A.26.3） | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_A.26.3.html> |
| 3 | DICOM PS3.3 C.8.1 CR Modules（C.8.1.1・C.8.1.2） | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.html> |
| 4 | DICOM PS3.3 C.7.6 Common Image IE Modules（C.7.6.1） | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.html> |
| 5 | DICOM PS3.3 C.8.11.1 DX Series Module | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.11.html> |
| 6 | DICOM PS3.3 C.8.11.2 DX Anatomy Imaged Module | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.11.2.html> |
| 7 | DICOM PS3.3 C.8.11.3 DX Image Module | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.11.3.html> |
| 8 | DICOM PS3.3 C.8.11.4 DX Detector Module | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.11.4.html> |
| 9 | DICOM PS3.3 C.8.11.5 DX Positioning Module | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.11.5.html> |
| 10 | DICOM PS3.4 B.5 Standard SOP Classes | <https://dicom.nema.org/medical/dicom/current/output/chtml/part04/sect_B.5.html> |
| 11 | DICOM PS3.16 CID 4031 Common Anatomic Region | <https://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_CID_4031.html> |
| 12 | DICOM PS3.16 CID 4010 DX View | <https://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_CID_4010.html> |

シリーズの並びと枚数の出典は、前の change の design.md の「出典」（AAPM の
プロトコル集、Radiopaedia、Canon・OHSU の MR のプロトコルなど）にある。
