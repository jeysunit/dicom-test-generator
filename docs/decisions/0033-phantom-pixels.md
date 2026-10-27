# ADR-0033: 図形の画素は、患者座標で評価した幾何学の図形にし、偽物の印はタグに書く

- 状態：提案
- 作成日：2026-10-27
- 最終更新日：2026-10-27

## 背景

画素の方式は `simple_text` と `ct_realistic`（[ADR-0005](0005-pixel-modes.md)）の
2つで、どちらも1つのシリーズの全画像が同じ絵になる。PACS のビューアでスライスを
送っても、位置が動いたことが画像から分からない。部位とも結び付かないので、頭部の
検査と胸部の検査が同じ絵になる。

一方、DTG の画素は合成したもので、臨床には使えない（project_charter の 1 章）。
それらしい画像に近づけるほど、本物の画像と取り違えられやすくなる。

実務の CT・MR・CR/DX の画像に、文字の焼き込みはまれである（セカンダリー
キャプチャを除く）。患者 ID を画素に描くと、タグを消すだけでは匿名化にならず、
PS3.15 の Clean Pixel Data Option の処理が要る（PS3.15 E.3.1）。

## 決定

1. 画素の方式に `phantom`（図形）を足す。各画素の患者座標で3次元の図形を評価する。
   図形の中心と半径は1回の撮影（同じ Frame of Reference UID）で一度だけ決めるので、
   軸位・冠状断・矢状断は同じ図形の断面になり、スライスの位置が変われば断面の
   大きさが変わる。`phantom` のときは、冠状断と矢状断の画像（CT の位置決めと、MR の
   ローカライザーの冠状断・矢状断の断面を含む）を軸位の範囲を覆う位置に置く（今の
   位置は軸位とほとんど交わらない）
2. 基本の図形は回転楕円体1つと、シリーズの中の番号で角度を変える位置の目印にする。
   ルーチンに部位（`phantom`）を書けば、部位の図形（楕円体・楕円柱・円柱・直方体と
   その殻の組）にする
3. 図形は区分ごとに一定の値で描き、ノイズ・ぼかし・臓器や骨の輪郭を描かない
4. 既定では画素に文字を描かない。偽物の印はタグに書き、Manufacturer (0008,0070) と
   Manufacturer's Model Name (0008,1090) を `DTG SYNTHETIC`、Image Comments
   (0020,4000) を `SYNTHETIC TEST DATA`、Burned In Annotation (0028,0301) を `NO`、
   Recognizable Visual Features (0028,0302) を `NO` にする（PS3.3 C.7.6.1）。
   これらは `phantom` で画素を作った画像だけに書き、装置のプロファイルの値より
   優先する
5. 文字の焼き込みは、選んだときだけ使う変種にする（`burn_in`）。上端の帯に
   `TEST / SYNTHETIC`・患者 ID・検査日・何枚目か・位置を英字で、画素の値の最小と
   最大だけで描き、そのときだけ Burned In Annotation を `YES` にする。匿名化の道具が
   焼き込みを見つけられるかの試験に使う
6. 既定の方式は `ct_realistic` のままにし、`phantom` は Job・CLI・設定で選んだとき
   だけ使う

## 検討した選択肢

- 今の方式のまま、シリーズの中の番号の文字だけを描く：作りは小さいが、MPR や
  スライスを送る試験で、断面の大きさの変化を見られない
- 公開のファントムや実の画像を加工して使う：本物らしくなりすぎ、偽物と分からない。
  ライセンスの確かめも要る
- 既定を `phantom` に変える：今の Job と試験の画素が変わる。利用者が選ぶまで変えない
- `phantom` の既定で患者 ID と検査日を焼き込み、Burned In Annotation を `YES` に
  する：実務の画像の形から離れ、タグを消すだけでは匿名化にならない画像が既定に
  なる。焼き込みは選んだときだけにする
- 例の装置のプロファイルとテンプレートの Manufacturer を `DTG SYNTHETIC` に変える：
  既定の撮影の値と、今の試験の期待値（12 のファイル）が変わる

## 結果

- スライスを送ると図形が変わる。偽物の印は Manufacturer と Image Comments で見える
- Basic Profile で匿名化すると Image Comments は消える。Manufacturer は Basic
  Profile の消す対象に入っていない（PS3.15 Table E.1-1）
- `phantom` の画像は、装置のプロファイルを当てても Manufacturer と Manufacturer's
  Model Name が `DTG SYNTHETIC` になる。ほかの装置の値はプロファイルのまま
- 画素の方式が3つになり、spec/02・06・07 と CLI の選択肢が増える
- 焼き込みを選んだときの文字は Pillow の既定のフォントで描くので、日本語は描かない

## 決めないこと

- PET の画素（PT のシリーズは今の画素のまま）
- US の画像

## 出典

- PS3.3 C.7.6.1（General Image Module の Burned In Annotation・Recognizable Visual
  Features）、C.7.6.2（Image Plane Module）
- PS3.15 E.3.1（Clean Pixel Data Option）、Table E.1-1（Application Level
  Confidentiality Profile Attributes）

## 関連

- [ADR-0005](0005-pixel-modes.md)：画素の方式
- [ADR-0025](0025-exam-routines.md)：撮影のルーチン
- `openspec/changes/add-modality-synthetic-images/`
