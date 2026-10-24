# exam-routines Specification

## Purpose

撮影のルーチン（部位ごとのシリーズの並びと画像数）と、予約へのルーチンの当て方、
CT のシリーズの種類ごとの DICOM の値、ルーチンに書いたシリーズ番号の扱いを定める
（ADR-0025）。

## Requirements

### Requirement: 予約に合うルーチンを既定で当てる

DTG は、撮影の画面を開いたとき（CLI では `-s`・`-i`・`--routine` を省いたとき）、
予約のモダリティと同じモダリティのルーチンから1つを当て、そのルーチンの並びと
画像数を既定にしなければならない（SHALL）。予約の検査の記述と部位（Body Part
Examined (0018,0015) があれば）に、ルーチンの YAML の `keywords`（見出しの言葉）が
含まれるルーチンを当て、どれも当たらなければそのモダリティの既定のルーチン（CT は
胸部 単純）とする。施設の検査のコードの対応表は使わない。撮影の画面は、当てた
ルーチンを最初から選んだ状態で出す。予約のモダリティが空なら、テンプレートの
モダリティを使う。緊急の患者（予約なし）は、テンプレートのモダリティの既定の
ルーチンにする。

#### Scenario: 検査名で当てる

- **WHEN** モダリティ CT、Requested Procedure Description「胸部単純CT」の予約で撮影の画面を開く
- **THEN** ルーチン「胸部 単純」が選ばれ、シリーズの行が 6 つ入り、画像数は上から 1・60・60・300・83・1 になる

#### Scenario: 長い語が勝つ

- **WHEN** Requested Procedure Description「胸腹部造影CT」の予約で撮影の画面を開く
- **THEN** ルーチン「胸腹部骨盤 造影」が選ばれる

#### Scenario: 見出しの言葉で当てる

- **WHEN** Requested Procedure Description「肝ダイナミックCT」の予約で撮影の画面を開く
- **THEN** 長い語「ダイナミック」が当たり、ルーチン「肝臓 ダイナミック」が選ばれた状態で出る

#### Scenario: 部位で当てる

- **WHEN** 検査の記述が2つとも「単純CT」で、Body Part Examined が `HEAD` の予約で撮影の画面を開く
- **THEN** ルーチン「頭部 単純」が選ばれる

#### Scenario: 緊急の患者

- **WHEN** テンプレート `ct_generic` で、予約なしの緊急の患者の撮影の画面を開く
- **THEN** CT の既定のルーチン「胸部 単純」が選ばれた状態で出る

#### Scenario: モダリティが空の予約

- **WHEN** テンプレートが CT で、Modality が空、検査名が「頭部」の予約で撮影の画面を開く
- **THEN** CT のルーチンから「頭部 単純」が選ばれる

#### Scenario: 当たらない

- **WHEN** モダリティ CT、検査の記述が「特殊検査」で Body Part Examined の無い予約で撮影の画面を開く
- **THEN** CT の既定のルーチン「胸部 単純」が選ばれる

#### Scenario: 何も選ばずに撮影する

- **WHEN** 検査名「胸部単純CT」の予約で撮影の画面を開き、何も変えずに「撮影」を押す
- **THEN** 6つのシリーズ、合計 505 枚の画像が作られる

#### Scenario: CLI で何も指定しない

- **WHEN** 検査名「胸部単純CT」の予約で、`-s`・`-i`・`--routine` を付けずに `exam` を実行する
- **THEN** 「胸部 単純」の並びで 505 枚の画像が作られ、結果に使ったルーチンの名前が出る

#### Scenario: 既定の無いモダリティ

- **WHEN** `templates/routine/` の CT のルーチンに `default: true` が1つも無いか、2つある
- **THEN** ルーチンは読み込まれず、設定の誤りとして知らせる

### Requirement: 見出しの言葉を決まった順で比べる

DTG は、予約の欄でルーチンを当てるとき、Requested Procedure Description、
Scheduled Procedure Step Description、Body Part Examined の順に見て、先の欄で
当たれば後の欄を見てはならない（SHALL NOT）。1つの欄でいくつかの語が当たれば長い
語のルーチン、同じ長さなら欄の中で前に出てくる語のルーチンとする。欄と語は NFKC で
正規化し、大文字と小文字を区別せずに比べ、長さは正規化した後の文字数で数える。
同じモダリティの2つのルーチンに、正規化した後に同じになる語があれば、読み込みの
誤りとする。

#### Scenario: 先の欄が勝つ

- **WHEN** Requested Procedure Description が「腹部CT」、Scheduled Procedure Step Description が「胸腹部」の予約で撮影の画面を開く
- **THEN** ルーチン「腹部骨盤 単純＋造影」が選ばれる（Requested Procedure Description で当たったので、Scheduled Procedure Step Description は見ない）

#### Scenario: 全角と大文字

- **WHEN** Requested Procedure Description が「ＣＨＥＳＴ ct」の予約で撮影の画面を開く
- **THEN** 語「CHEST」が当たり、ルーチン「胸部 単純」が選ばれる

#### Scenario: 同じ長さの語

- **WHEN** Requested Procedure Description が「頭部・胸部CT」の予約で撮影の画面を開く
- **THEN** 前に出てくる「頭部」のルーチン「頭部 単純」が選ばれる

#### Scenario: 2つのルーチンに同じ語

- **WHEN** CT の2つのルーチンの `keywords` に、どちらも「胸部」がある
- **THEN** ルーチンは読み込まれず、重なった語と2つのファイルの名前を知らせる

### Requirement: ルーチンを変えられ、手でも入れられる

撮影の画面は、撮影の設定に「ルーチン」の選択を持ち、当てたルーチンを別の
ルーチンに変えられなければならない（SHALL）。並べるのは、予約のモダリティと同じ
ルーチンと「手で入れる」とする。すべてのシリーズの画像数にはルーチンの既定の値が
入る。画像数は手で変えられ、シリーズを外せる。「手で入れる」を選んだら、今の
シリーズ数と画像数の欄にする。ルーチンの YAML で画像数を書いていないシリーズが
あれば、そのルーチンは読み込みの誤りとする。

#### Scenario: 別のルーチンに変える

- **WHEN** 「胸部 単純」が当たった予約で、ルーチンを「胸腹部骨盤 造影」に変える
- **THEN** シリーズの行は「胸腹部骨盤 造影」の 6 つになり、画像数は上から 1・150・133・83・116・1 になる

#### Scenario: 画像数の無いルーチン

- **WHEN** `templates/routine/` に、`images` を書いていないシリーズを含むルーチンの YAML がある
- **THEN** そのルーチンは読み込まれず、設定の誤りとしてファイルの名前とシリーズの位置を知らせる

#### Scenario: 画像数を変えて撮影する

- **WHEN** 「胸部 単純」の 4 行目の画像数を 300 から 50 に変えて撮影する
- **THEN** 4つ目のシリーズの画像は 50 枚になり、ほかのシリーズはルーチンの枚数になる

#### Scenario: 手で入れる

- **WHEN** ルーチンで「手で入れる」を選び、シリーズ数 2・画像数 `1,20` で撮影する
- **THEN** 今と同じく、CT の軸位の画像が 1 枚と 20 枚の2つのシリーズで作られる

### Requirement: モダリティごとの形のルーチンを持つ

DTG は、DTG が扱うモダリティ（CT・MR・CR・DX・US）ごとに、そのモダリティの形の
ルーチンを持たなければならない（SHALL）。CT はシリーズの種類と再構成、MR は
シーケンス（ADC は DWI と別のシリーズ）、CR は方向ごとに1シリーズ1枚、DX は
1シリーズに全部の方向、US は静止画と動画の数を持つ。どのルーチンも、すべての
シリーズに既定の画像数を持ち、各モダリティに既定のルーチンが1つある。画像を
作れないモダリティ（今は CT 以外）の予約は、今の決まりどおり、テンプレートの
モダリティと違うことを知らせて撮影しない。

#### Scenario: MR のルーチン

- **WHEN** `templates/routine/` の MR のルーチンを読み込む
- **THEN** 頭部・腰椎・膝・肩の4つがあり、既定は頭部で、頭部の並びはローカライザー 15 枚から始まり、ADC は DWI と別のシリーズになっている

#### Scenario: CR と DX の胸部

- **WHEN** CR と DX の「胸部」のルーチンを読み込む
- **THEN** どちらも PA と側面の各1枚で、CR は2つのシリーズ、DX は1つのシリーズになっている

#### Scenario: MR の予約

- **WHEN** テンプレートが CT だけのときに、モダリティ MR の予約で撮影の画面を開く
- **THEN** MR の既定のルーチン「頭部」が当たるが、今と同じく「予約は MR、テンプレートは CT です」と知らせて撮影は押せない

### Requirement: シリーズの種類ごとに DICOM の値を変える

DTG は、ルーチンのシリーズの種類に合わせて、Image Type (0008,0008)・Image
Orientation (Patient) (0020,0037)・SOP Class UID を変えなければならない（SHALL）。
位置決めは `ORIGINAL\PRIMARY\LOCALIZER`、軸位は `ORIGINAL\PRIMARY\AXIAL`、
冠状断と矢状断は `DERIVED\SECONDARY\AXIAL`（PS3.3 C.8.2.1.1.1）にする。線量の
画面は Secondary Capture Image Storage で作り、Modality は CT にする。Series
Description (0008,103E) と Protocol Name (0018,1030) はルーチンの値にする。軸位・
冠状断・矢状断の Slice Thickness (0018,0050) と画像の位置の間隔は、ルーチンの
`slice_thickness` にする。位置決めの画像の向きは、ルーチンの `views` の画像ごとの
方向にする。

#### Scenario: 位置決めの画像

- **WHEN** 正面の位置決めのシリーズを作る
- **THEN** Image Type は `ORIGINAL\PRIMARY\LOCALIZER`、Image Orientation (Patient) は `1\0\0\0\0\-1`、SOP Class は CT Image Storage になる

#### Scenario: 線量の画面

- **WHEN** 線量の画面のシリーズを作る
- **THEN** SOP Class は Secondary Capture Image Storage（1.2.840.10008.5.1.4.1.1.7）、Modality は CT、Image Type は `DERIVED\SECONDARY`、Conversion Type は `WSD`、Patient Orientation は空の値になり、Image Position (Patient)・Image Orientation (Patient)・Frame of Reference UID・Rescale Intercept は無い

#### Scenario: 冠状断の画像

- **WHEN** 冠状断のシリーズを 3 枚作る
- **THEN** Image Type は `DERIVED\SECONDARY\AXIAL`、Image Orientation (Patient) は `1\0\0\0\0\-1` で、Image Position (Patient) は画像ごとに前後の向き（y）に進む

#### Scenario: スライス厚と画像の間隔

- **WHEN** ルーチンで `slice_thickness: 3.0` の軸位のシリーズを作る
- **THEN** そのシリーズの画像の Slice Thickness は 3.0 で、隣の画像との Image Position (Patient) の z の差は 3.0 になる

#### Scenario: 2方向の位置決め

- **WHEN** `images: 2`・`views: ["frontal", "lateral"]` の位置決めのシリーズを作る
- **THEN** 1枚目の Image Orientation (Patient) は `1\0\0\0\0\-1`、2枚目は `0\1\0\0\0\-1` になる

#### Scenario: 位置決めの画像数を増やす

- **WHEN** `views: ["frontal", "lateral"]` の位置決めの画像数を、撮影の画面で 3 に変えて撮影する
- **THEN** 3枚の向きは、正面・側面・正面になる

#### Scenario: 造影のシリーズ

- **WHEN** ルーチンで `contrast: true` のシリーズを作る
- **THEN** そのシリーズの画像に Contrast/Bolus Agent (0018,0010) が入り、`contrast` の無いシリーズの画像には入らない

#### Scenario: 手で入れたシリーズ

- **WHEN** 「手で入れる」で撮影する
- **THEN** すべてのシリーズの画像は今と同じ CT の軸位の画像（`ORIGINAL\PRIMARY\AXIAL`）になる

### Requirement: ルーチンに書いたシリーズ番号がぶつかったら撮影しない

DTG は、予約ごとに使ったシリーズ番号を記録し、ルーチンで書いたシリーズ番号が、
使った番号か同じ撮影のほかのシリーズの番号と同じなら、撮影せずに止めなければ
ならない（SHALL）。番号を書かないシリーズには、自動で付けた番号の最大の次の
番号を付け、それが使った番号なら、空いている番号まで進める。

#### Scenario: 追加撮影で 999 がぶつかる

- **WHEN** 線量の画面をシリーズ 999 にするルーチンで撮影した予約で、同じルーチンで追加撮影する
- **THEN** 画像は作られず、シリーズ番号 999 が既にあることを知らせる

#### Scenario: 書いた番号の後の自動の番号

- **WHEN** シリーズ番号 1・2・3 を自動で、501 をルーチンに書いて撮影した予約で、「手で入れる」で1シリーズを追加撮影する
- **THEN** 追加したシリーズの番号は 4 になる

#### Scenario: 自動の番号が書いた番号に当たる

- **WHEN** シリーズ番号 1・2・3 を自動で、4 をルーチンに書いて撮影した予約で、「手で入れる」で1シリーズを追加撮影する
- **THEN** 追加したシリーズの番号は 5 になる

### Requirement: CLI でルーチンを指定できる

CLI の `exam` は、`--routine 名前` でルーチンを指定できなければならない（SHALL）。
`-s`・`-i` と同時に指定したら、撮影せずに入力の誤りの終了コード 4 で終了する。

#### Scenario: CLI でルーチンを使う

- **WHEN** `exam --routine ct_chest_plain` を実行する
- **THEN** 「胸部 単純」のシリーズの並びで画像が作られる

#### Scenario: -s と同時に指定する

- **WHEN** `exam --routine ct_chest_plain -s 2` を実行する
- **THEN** 画像は作られず、終了コード 4 で終了する

#### Scenario: 画像数を変える

- **WHEN** `exam --routine ct_chest_plain --routine-images 1,60,60,50,83,1` を実行する
- **THEN** 4つ目のシリーズの画像は 50 枚になり、ほかはルーチンの枚数になる

#### Scenario: 画像数の数がシリーズの数と違う

- **WHEN** `exam --routine ct_chest_plain --routine-images 1,60` を実行する
- **THEN** 画像は作られず、終了コード 4 で終了する

### Requirement: 外したシリーズを戻せる

撮影の画面は、ルーチンの表で「外す」を押した行を、表から消さずに薄く表示し、撮影の
対象から外さなければならない（SHALL）。外した行の画像数の欄は押せなくし、ボタンを
「戻す」に替える。「戻す」を押すと、その行は外す前の画像数のまま撮影の対象に戻る。
撮影の対象の最後の1行は外せない。

#### Scenario: 外して戻す

- **WHEN** 「胸部 単純」の 4 行目の画像数を 300 から 50 に変え、その行の「外す」を押してから「戻す」を押す
- **THEN** 4 行目は撮影の対象に戻り、画像数は 50 のままになる

#### Scenario: 外した行は撮らない

- **WHEN** 「胸部 単純」の 3 行目の「外す」を押して撮影する
- **THEN** 3 行目は薄く表示されたまま残り、撮影の要求に入らず、そのシリーズの画像は作られない

#### Scenario: 対象の最後の1行

- **WHEN** 「頭部 単純」の4行のうち3行を外す
- **THEN** 残った1行の「外す」は押せない。外した3行の「戻す」は押せる

### Requirement: 撮影の要求の間はルーチンの欄を操作できない

撮影の画面は、撮影の要求を送ってから応答が返るまで、ルーチンの欄（選択・画像数・
「外す」・「戻す」）を操作できないようにしなければならない（SHALL）。要求に入る値は
送った時点の値のままとする。

#### Scenario: 撮影の応答を待つ間

- **WHEN** 「撮影」を押し、応答が返る前にルーチンの画像数の欄を押す
- **THEN** 欄は操作できず、応答が返った後は操作できる

### Requirement: 数の欄の検証の文言は日本語で出す

撮影の画面の画像数・シリーズ数の欄は、範囲の外の値や空の値を送ろうとしたとき、
ブラウザの言語に従う文言ではなく、画面のほかの知らせと同じ日本語の文言を出さなければ
ならない（SHALL）。範囲は欄の最小・最大から読む。値を直したら、文言は消える。

#### Scenario: 画像数が範囲の外

- **WHEN** ルーチンの「Scout」の行の画像数に 0 か 1001 を入れて撮影を押す
- **THEN** 「Scout の画像数は 1〜1000 で入れてください」が出て、撮影の要求は送られない

#### Scenario: シリーズ数が空

- **WHEN** 「手で入れる」でシリーズ数を空にして撮影を押す
- **THEN** 「シリーズ数を入れてください」が出る
