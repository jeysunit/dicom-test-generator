# Proposal

## Why

DTG が画像を作れるモダリティは CT・MR・PT だけで、CR と DX は作れない。ルーチン
（`templates/routine/` の `cr_*`・`dx_*` の 12 本）はあるが、CR・DX のテンプレートと
画像を作る処理が無い。CR・DX の予約は、合うテンプレートが無いので「予約は CR、
テンプレートは CT です」と知らせて撮影しない。

画素も、検査の中身と結び付いていない。今の方式は `simple_text`（SOP Instance UID の
文字）と `ct_realistic`（`gradient`・`circle`・`noise`）の2つで、どちらも1つの
シリーズの全画像が同じ絵になる（`noise` は乱数なので画像ごとに違うが、位置とは
関係しない）。そのため、PACS のビューアでスライスを送っても、位置が動いたことが
画像から分からない。頭部の検査と胸部の検査も同じ絵になる。

依頼者が求めたのは次の3つである。

- シリーズの中でスライスの位置が動いたことが分かるように、画像を少しずつ変える
- 検査の内容に合わせて、それらしい画像にする。ただし、明らかに偽物と分かること
- CT・MR・CR/DX の画像を、モダリティごとの検査のシリーズの構成で作る

## What Changes

この change は4つの PR に分けて入れる（design.md の「PR の分け方」）。

- 画素の方式に `phantom`（図形）を足す。画素の患者座標で3次元の図形を評価するので、
  スライスの位置が変われば図形の断面の大きさが変わる。位置の目印（小さい四角）が
  画像の番号に合わせて円の上を回る。画素に文字は描かない。偽物の印はタグに書き、
  Manufacturer と Manufacturer's Model Name を `DTG SYNTHETIC`、Image Comments
  (0020,4000) を `SYNTHETIC TEST DATA`、Burned In Annotation (0028,0301) を `NO` に
  する（基本の図形。PR 1）
- 文字の焼き込みは、選んだときだけ使う変種として足す。上端の帯に `TEST / SYNTHETIC`・
  患者 ID・検査日・何枚目か・位置を英字で描き、そのときだけ Burned In Annotation を
  `YES` にする。匿名化の道具が焼き込みを見つけられるかの試験に使う（焼き込み。PR 4）
- CR の画像を CR Image Storage、DX の画像を Digital X-Ray Image Storage - For
  Presentation で作る。テンプレート `cr_generic`・`dx_generic` と、例の装置の
  プロファイルを足す。CR・DX の予約と緊急の患者を、画面と CLI で撮れるようにする
  （PR 2）
- `phantom` の図形を、ルーチンの部位ごとに変える（部位の図形。PR 3）。頭部は楕円の骨の輪と
  その中、胸部は暗い肺の楕円2つ、腹部は大きさの違う楕円と血管の円、脊椎は骨の
  ブロックの列、四肢は2本の骨の円柱とする。MR はシリーズの強調（T1・T2・FLAIR・
  DWI・ADC・MRA など）で区分ごとの信号の値を変え、CT の造影は相ごとに血管の値を変える
- どの図形も円・楕円・矩形・輪だけで描き、区分ごとに一定の値にする。ノイズ・ぼかし・
  臓器の輪郭は描かない（「明らかに偽物」の決まり）
- 既定は変えない。設定の `modality.default_pixel_mode`、CLI の `--pixel-mode`、
  Job の `pixel_spec.mode` の既定は今の `ct_realistic`（`gradient`）のままで、
  `phantom` は選んだときだけ使う

## 決めたこと

2026-10-27 に依頼者が次の 8 つを決めた。1 と 2 は提案の推奨を直した形で、3〜8 は
推奨のとおりである。

1. 既定の `phantom` の画素には文字を描かない。画素は図形と位置の目印だけにする。
   実務の CT・MR・CR/DX の画像に文字の焼き込みはまれで（セカンダリーキャプチャを
   除く）、既定の画像は実務に近い形にするため
2. Burned In Annotation は `NO` にする。偽物の印はタグに書き、Manufacturer
   (0008,0070) と Manufacturer's Model Name (0008,1090) を `DTG SYNTHETIC`、
   Image Comments (0020,4000) を `SYNTHETIC TEST DATA` にする。Recognizable Visual
   Features (0028,0302) は `NO` にする。患者 ID が画素にあると、タグを消すだけでは
   匿名化にならない（PS3.15 の Clean Pixel Data のオプションが要る）。文字の
   焼き込みは、選んだときだけ使う変種として残す。描く文字は英字だけ（`TEST /
   SYNTHETIC`・患者 ID・検査日・何枚目か・位置）で、そのときだけ Burned In
   Annotation を `YES` にする。匿名化の道具が焼き込みを見つけられるかの試験に使う
3. CR・DX の画素は 1024 列 × 1248 行に固定し、検出器の大きさを架空の約
   350 × 427 mm（Imager Pixel Spacing 0.342 mm）にする。PET が行列を 128 に固定して
   いるのと同じく、Job の `pixel_spec` の幅と高さには従わない。1枚は約 2.5 MB
4. CR・DX の Photometric Interpretation は、既定を `MONOCHROME2` にし、テンプレートで
   `MONOCHROME1` も選べるようにする。CR 装置は `MONOCHROME1` を出すことが多く、
   ビューアの白黒の反転の試験に使えるため
5. DX は For Presentation だけを作る。For Processing は CAD などの後処理の入力で、
   PACS の表示の試験には要らない
6. 対になる部位（膝・手）の左右は、CR・DX のルーチンの YAML の部位 `body_part` と
   左右 `laterality` で決め、付けるルーチンは架空の `R` にする。CR は Laterality
   (0020,0060) が `R`・`L` だけなので、両側（`B`）は DX だけで書ける。予約の検査の
   記述から左右を読み取る処理は作らない
7. PET はこの change の範囲に入れず、PT のシリーズは今の画素のままにする。PET/CT の
   検査で `phantom` を選ぶと、CT のシリーズだけが図形になる
8. 冠状断・矢状断の画像の位置は、`phantom` のときだけ、Image Position (Patient) の
   z を軸位の範囲の上端にする。今の冠状断は z が 0 以下の範囲を写し、軸位（z が
   0 以上）とほとんど交わらないので、図形がほぼ写らないため（design.md の「図形の
   置き方」）。既定の方式の位置は変えない

## Capabilities

### New Capabilities

- `synthetic-images`: 図形の画素の方式（`phantom`）、偽物の印と焼き込みの決まり、
  CR・DX の画像

### Modified Capabilities

- `exam-routines`: CR・DX のルーチンで画像を作れるようにし、ルーチンに部位の図形
  （`phantom`）・CR・DX の部位と左右（`body_part`・`laterality`）・MR の強調
  （`weighting`）・造影の相（`phase`）を
  書けるようにする

## Impact

- core：`app/core/pixel_generator.py`（図形の評価と、選んだときの焼き込み）、
  `app/core/generator.py`
  （CR Image・DX Image の Dataset）、`app/core/series_layout.py`（CR・DX の向きと
  Patient Orientation）、`app/core/models.py`（`PixelSpecPhantom`・シリーズの
  モダリティに CR・DX）、`app/core/routine.py`
- サービス：`app/services/study_generator.py`（モダリティごとの画素の振り分け）
- モダリティ：`app/modality/config.py`・`service.py`（`phantom` を選べるようにする）。
  CLI：`--pixel-mode` の選択肢に `phantom`
- テンプレート：`templates/modality/cr_generic.yaml`・`dx_generic.yaml`（新しい）、
  `templates/routine/` の各ルーチンに `phantom`・`body_part`・`laterality`・
  `weighting`・`phase`
- 装置のプロファイル：`profiles/examples/dtg_synthetic_cr.yaml`・`dtg_synthetic_dx.yaml`
  （新しい）、作れる SOP Class に CR・DX を足す
- spec：02 の 3 章、03、06 の 4 章と 5 章（CR・DX の節を足す。5.2 の「CR・US など
  を断る」は CR・DX を外す）、07 の 3.6、12a の CLI、13 の 4.3。ADR-0033・0034
- roadmap.md：「CT・MR・PT 以外のモダリティ」の行から CR・DX を外す
- 既定は変わらない。`phantom` を選ばない撮影と Job の画像は、今と同じ値になる。
  Manufacturer と Manufacturer's Model Name を `DTG SYNTHETIC` にするのは `phantom`
  の画像だけで、そのときは装置のプロファイルの値より優先する
