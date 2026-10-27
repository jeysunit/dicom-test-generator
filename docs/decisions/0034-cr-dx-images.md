# ADR-0034: CR・DX の画像は、CR Image Storage と DX の For Presentation で作る

- 状態：提案
- 作成日：2026-10-27
- 最終更新日：2026-10-28

## 背景

ルーチンには CR と DX の部位ごとの撮影の方向がある
（[ADR-0025](0025-exam-routines.md)）。しかし、CR・DX のテンプレートと画像を作る
処理が無いので、CR・DX の予約は撮影できない。PACS の試験では、CT・MR のほかに
一般撮影の画像も要る。

DX の IOD には For Presentation と For Processing の2つの SOP Class があり、画素の
表し方には `MONOCHROME1` と `MONOCHROME2` がある（PS3.3 A.26・C.8.11.3）。

## 決定

1. CR のシリーズは CR Image Storage（1.2.840.10008.5.1.4.1.1.1）で、方向ごとに
   1シリーズにする。View Position (0018,5101) は CR Series Module のシリーズの値
   だから（PS3.3 C.8.1.1）
2. DX のシリーズは Digital X-Ray Image Storage - For Presentation
   （1.2.840.10008.5.1.4.1.1.1.1）で、1シリーズに全部の方向を入れる。For Processing
   は作らない。For Processing は後処理の入力で、PACS の表示の試験には要らないため
3. Photometric Interpretation の既定は `MONOCHROME2` にし、テンプレートで
   `MONOCHROME1` を選べるようにする。`MONOCHROME1` ではビューアの白黒の反転を
   試せる
4. 画素は 1248 行 × 1024 列・Bits Stored 12・符号なしに固定し、Imager Pixel Spacing
   は架空の 0.342 mm にする。Job の画素の大きさには従わない（PET の行列と同じ扱い）
5. 部位と左右は、ルーチンの `body_part` と `laterality` で決める。CR の対になる
   部位は Laterality (0020,0060) に `R`・`L` だけを入れ（PS3.3 C.7.3.1）、DX は
   Image Laterality (0020,0062) に `R`・`L`・`B`、対にならない部位は `U` を入れる
   （C.8.11.2）。予約の記述から左右を読み取らない
6. CR・DX の画像は Frame of Reference と Image Plane を持たず、Patient Orientation
   (0020,0020) を持つ（PS3.3 C.7.6.1 の Type 2C、C.8.11.3 の Type 1C）
7. DX の Burned In Annotation (0028,0301) は DX Image Module で Type 1 なので、
   どの方式でも書く。値は `NO` で、`phantom` で焼き込みを選んだときだけ `YES` にする
   （C.8.11.3）。`phantom` の CR・DX の画像には、CT・MR と同じ偽物の印のタグを書く
   （[ADR-0033](0033-phantom-pixels.md)）
8. テンプレート `cr_generic`・`dx_generic` と、例の装置のプロファイルを足す。予約の
   モダリティに合うテンプレートを選ぶ決まりは [ADR-0030](0030-mr-images.md) のまま

## 検討した選択肢

- CR も DX の形（1シリーズに全部の方向）にする：CR Series Module の View Position
  がシリーズの値なので、方向の違う画像を1シリーズに入れると規格に合わない
- DX の For Processing も作る：取り込みの試験には別の価値があるが、For Processing
  の画素は表示に向かず、VOI LUT の扱いも違う。要るときに別の決定にする
- 画素を Job の幅と高さ（既定 512）にする：一般撮影の画像としては小さく、行と列の
  数が違う画像をビューアで試せない

## 結果

- CR・DX の予約と緊急の患者を、画面と CLI で撮れる
- 画像を作るモダリティは CT・MR・PT・CR・DX になる。US は今のまま、作る前に断る
- 1枚の画像は約 2.5 MB になる

## 決めないこと

- DX の For Processing、マンモグラフィ・口腔内撮影の IOD
- 撮影の条件（KVP・mAs・線量）の属性

## 出典

- PS3.3 A.2（CR Image IOD）、A.26（Digital X-Ray Image IOD）、C.8.1（CR Modules）、
  C.8.11（DX Modules）
- PS3.4 B.5（標準の SOP Class）
- PS3.16 CID 4010（DX View）、CID 4031（Common Anatomic Region）

## 関連

- [ADR-0025](0025-exam-routines.md)：撮影のルーチン
- [ADR-0030](0030-mr-images.md)：MR の画像とテンプレートの選び方
- [ADR-0033](0033-phantom-pixels.md)：図形の画素
- `openspec/changes/add-modality-synthetic-images/`
