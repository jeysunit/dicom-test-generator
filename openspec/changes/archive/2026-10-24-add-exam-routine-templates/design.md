# Design

## 決めたこと

proposal の「承認者が決めること」の 1〜3 は、どれも推奨の案に決めた（2026-10-24）。
画面の手入力の選択肢の表示は「手で入れる」。決めた内容は
[ADR-0025](../../../../docs/decisions/0025-exam-routines.md) にまとめた。

## 調べたこと

公開の資料で、モダリティごとの検査のシリーズの並びと画像数を調べた
（2026-10-24）。番号は末尾の「出典」の番号。DTG が扱うモダリティは CT・MR・CR・
DX・US で、今画像を作れるのは CT だけ（MR・CR・DX・US は
[roadmap.md](../../../../docs/roadmap.md) の今後の範囲）。ほかのモダリティ
（マンモグラフィ・RF・XA・NM など）は DTG の範囲に無いので調べていない。

位置決め・ローカライザー・線量の画面の枚数は資料にある。中間の断面のシリーズ
（軸位・冠状断・矢状断の再構成と、MR の撮像）の画像数を載せた公開の資料は、CT では
見つからず、MR は Canon の頭部の例（出典 24）だけだった。枚数の無いシリーズの
既定の画像数は、資料のスライス厚と間隔、想定した撮影範囲から計算する（「既定の
画像数の決め方」）。

### 承認者の見立てと資料

承認者の見立ては「1シリーズ目は1枚、最終シリーズは2枚が多い、中間のシリーズは
部位で決まる」で、CT と MR の事例として話したもの。

| 見立て | CT | MR |
|--------|----|----|
| 1シリーズ目は1枚 | 当たる。位置決めで 1〜2 枚。頭部は側面 1 枚（正面は任意）、胸部は正面 1 枚（出典 3, 4） | 当たらない。1シリーズ目はローカライザーだが、3面を1シリーズに入れ、1面に 5〜8 枚の例がある（出典 26）。Siemens の装置の例でも最初のシリーズは `Localizer`（出典 27） |
| 最終シリーズは2枚 | 一般には当たらない。最後は線量の画面で、画面1つなら 1 枚（出典 1, 2）。2 に見えるのは、長い検査で画面が2枚に分かれるとき（出典 7）と、GE のように線量の画面（シリーズ 999）と RDSR（シリーズ 997。画像ではない）が並ぶとき（出典 1） | 当たらない。資料の並びの最後は撮像のシーケンス（出典 24, 25）。Siemens の装置は最後に `PhoenixZIPReport` のシリーズを置く例があるが、撮像のデータを持たない（出典 27） |
| 中間は部位で決まる | 当たる。プロトコル集は部位ごとに送るシリーズの名前を並べ、「臨床の目的で再構成を足す」と書く（出典 4, 5） | 当たる。部位ごとにシーケンスの組み合わせが決まる（出典 24, 28, 29） |

### CT の部位ごとの並び

位置決めの呼び名は会社ごとに違う（GE は scout、Philips は surview、Siemens は
topogram、東芝は scanogram。出典 16）。表の Series Description は資料の例で、
会社と施設で違う。

| 部位 | シリーズの並び（Series Description の例） | 出典 |
|------|------------------------------------------|------|
| 頭部（単純） | 位置決め（側面。正面は任意）／ AX（5mm）／ AX BONE（2〜2.5mm）／ SAG・COR（施設による） | 3, 5 |
| 胸部（単純） | 位置決め（正面）／ 縦隔の AX（5mm）／ 肺野の AX（5mm）／ MIP／ COR・SAG | 4, 5 |
| 胸腹部骨盤（造影） | 位置決め／ Ax Chest（2mm）／ Ax A/P（3mm）／ 胸と腹部骨盤の Cor・Sag | 5, 6 |
| 腹部骨盤（単純＋造影） | 位置決め／ AX／ AX +C／ AX DEL／ COR／ COR +C／ SAG／ SAG +C | 5, 11 |
| 肝臓のダイナミック | 位置決め／ 動脈相 AX／ 門脈相 AX／ 平衡相 AX（各 3mm）／ 各相の COR・SAG | 5, 12, 13 |
| 冠動脈 CTA | 位置決め／ 石灰化スコア（3mm）／ 造影の CTA の軸位（0.5mm 前後） | 14, 15 |
| 腰椎 | 位置決め／ AX・SAG・COR の BONE と SOFT（各 2mm） | 5 |

日本医学放射線学会のガイドラインは、肝臓の CT で動脈相を含む多相の撮影と、
5mm 以下の再構成を求める（出典 12）。

### CT の線量の画面と RDSR

- 多くの CT は、シリーズごとの CTDI と DLP を並べた画面を Secondary Capture の
  画像として保存する（出典 2）
- 会社ごとの違い（出典 1。2010 年の資料で、今の装置では確かめていない）：
  - GE：線量の画面はシリーズ 999、Image Type `DERIVED\SECONDARY\SCREEN SAVE`。
    RDSR はシリーズ 997
  - Siemens：線量の画面（Patient Protocol）はシリーズ 501、Image Type
    `DERIVED\SECONDARY\OTHER\CT_SOM5 PROT`
  - Philips：Image Type に `DOSE_INFO`・`DOSE-INFO` などを含む。線量の集計の
    OSS の OpenREM は、Philips の線量の画面を Series Description `Dose Info` の
    Secondary Capture として読む（出典 23）
- 線量の画面の見た目（表の列と並び）は会社ごとに違う（出典 21）
- Siemens は、線量の画面をプロトコルごとに PACS へ自動で送る設定を持つ
  （出典 8）。送らない施設もある（推測。送らない設定の例は見つからなかった）

### CT の画像の種類と Image Type

- CT Image Module の Image Type の Value 3 の定義は `AXIAL`（断面の画像）と
  `LOCALIZER`（位置決めの画像）（PS3.3 C.8.2.1.1.1。出典 10）。同じ節の注は、
  断面の画像に冠状断・矢状断・斜断を含める。冠状断・矢状断も `AXIAL` にする
- Rescale Intercept の説明は、Value 1 が `ORIGINAL` で Value 3 が `LOCALIZER`
  でない画像の出力の単位を HU と定める。位置決めの画像は HU でなくてよい（出典 10）
- 位置決めの画像が軸位のシリーズに混ざって届く例もある（血管撮影の装置。出典 9）。
  DTG は位置決めを別のシリーズにする
- Siemens のワークステーションの MPR・MIP は `DERIVED\SECONDARY\AXIAL` に
  会社の Value 4 を付ける（出典 22）

### MR の部位ごとの並び

| 部位 | シリーズの並び | スライス厚／間隔 | 出典 |
|------|----------------|------------------|------|
| 頭部（脳梗塞の疑い） | ローカライザー／ DWI（b=1000）／ ADC／ T2*／ T1／ T2／ FLAIR／ MRA | Canon の例は 2D がすべて 5mm／1mm・25 枚、MRA は 116 枚。OHSU の例は DWI 3mm／0.3mm、T2*・T1・T2 は 4mm／1mm | 24, 25 |
| 腰椎 | ローカライザー／ 矢状断 T1／ 矢状断 T2／ 軸位 T2（脂肪抑制の T2 は任意） | 資料に厚さの例が無い。下の既定は 3mm／0.3mm（膝・肩の例と同じ）とした | 28 |
| 膝 | ローカライザー／ 矢状断 PD FS／ 冠状断 T2 FS／ 軸位 PD FS／ T1（1方向） | 3mm か 4mm | 29 |

- ローカライザー：3面を1シリーズにし、1面に 5〜8 枚（出典 26）
- DWI と ADC：OHSU の例は「b1000 と ADC だけを送る」（出典 25）。ADC は計算した
  画像で、Image Type の Value 1 は `DERIVED`（PS3.17 の Parametric Map の例は
  `DERIVED\PRIMARY\DIFFUSION\ADC`。出典 30）
- 肩の例（出典 26）：軸位 T2 FS・冠状断 T2 FS・冠状断 T1・矢状断 T1、どれも
  3.0mm／0.3mm

### CR・DX の撮影の方向

| 部位 | 方向 | 枚数 | 出典 |
|------|------|------|------|
| 胸部 | PA（立位）・側面（左側面） | 2 | 31 |
| 腹部 | AP（臥位）・PA（立位）。英国では臥位の1枚が普通 | 2 | 37 |
| 腰椎 | AP か PA・側面。斜位・屈曲と伸展は追加 | 2 | 32 |
| 頸椎 | AP・側面・開口（歯突起）。CT が無ければ斜位の2枚を足す | 3 | 38 |
| 膝 | AP・側面。スカイラインは追加 | 2 | 33 |
| 手 | PA・斜位・側面 | 3 | 39 |

- CR は View Position (0018,5101) が CR Series Module にある（PS3.3 C.8.1.1。
  出典 34）。シリーズの中の画像は同じ方向になるので、方向ごとに1シリーズにする
- DX は View Position が DX Positioning Module（画像ごと）にある（PS3.3
  C.8.11.5。出典 35）。方向の違う画像を1シリーズに入れられる

### US の静止画

- 腹部：ある施設の人間ドックの記録は、所見が無ければ3断面（肝腎コントラスト・
  胆嚢の長軸と短軸）だった。腹部超音波検診判定マニュアルは16断面以上を勧め、
  その施設は22断面に増やした（出典 36）
- 甲状腺・乳腺・心エコーの標準の断面の数と、動画（クリップ）の本数・フレーム数は、
  公開の資料の本文で確かめられなかった（「読めなかった頁」）

## 既定の画像数の決め方

ルーチンを選ぶだけで、すべてのシリーズに画像数が入る。利用者は変えなくても
撮影できる。中間のシリーズの画像数は次の式で計算し、小数は切り捨てる。

- CT の再構成：画像数 ＝ 撮影範囲 ÷ スライス厚（隙間の無い再構成として）
- MR の 2D の撮像：画像数 ＝ 撮影範囲 ÷（スライス厚 ＋ 間隔）
- 位置決め・ローカライザー・線量の画面・一般撮影は、資料の枚数をそのまま使う

撮影範囲は、資料の「どこからどこまで」（頭部は頭蓋底から頭頂、胸部は肩の上から
肝臓の中ほど。出典 3, 4）を、成人の体格で長さにした想定の値で、資料の値では
ない。

| 範囲の名前 | 想定の長さ | 使う向き |
|------------|-----------|----------|
| 頭部 | 150mm | CT の軸位 |
| 胸部 | 300mm | CT の軸位 |
| 腹部骨盤 | 400mm | CT の軸位 |
| 肝臓 | 250mm | CT の軸位 |
| 心臓 | 140mm（石灰化スコアは 120mm） | CT の軸位 |
| 腰椎の長さ | 150mm | CT・MR の軸位 |
| 体の前後 | 250mm | 冠状断（前後に並ぶ） |
| 体の左右 | 350mm | 矢状断（左右に並ぶ） |
| 腰椎の前後・左右 | 60mm | 腰椎の冠状断・矢状断 |
| MR の頭部 | 150mm | 25 枚 ×（5mm＋1mm）。出典 24 の値 |
| 膝 | 100mm | MR の膝の各面 |
| 肩 | 80mm | MR の肩の各面 |

## DTG に付けるルーチン

`templates/routine/` に、モダリティごとのルーチンを付ける。合計は1回の撮影の上限
（既定 2000）に収める。「既定」の印のルーチンは、予約に合うルーチンが無いときに
使うそのモダリティの既定（「既定のルーチンの当て方」）。

### ルーチンの形

| モダリティ | 1シリーズの持つ値 | シリーズの切り方 |
|------------|-------------------|------------------|
| CT | 種類（位置決め・軸位・冠状断・矢状断・線量の画面）・Series Description・画像数・スライス厚・造影の有無 | 種類と再構成ごと |
| MR | 種類（ローカライザー・撮像・計算した画像）・Series Description・面・画像数・スライス厚・間隔 | シーケンスごと。ADC は DWI と別のシリーズ |
| CR | 方向（View Position）・Series Description | 方向ごとに1シリーズ1枚（View Position がシリーズの値なので） |
| DX | 方向の並び | 1回の撮影の方向を1シリーズにまとめる（View Position が画像ごとの値なので） |
| US | 静止画の枚数・動画の本数とフレーム数 | 検査で1シリーズ（推測。US の画像を作る change で確かめる） |

MR・CR・DX・US のルーチンは、この change で YAML と当て方までを入れる。画像を
作る処理は、そのモダリティのテンプレートを足す change（roadmap の「CT 以外の
モダリティ」）で入れる。それまでは、予約のモダリティとテンプレートのモダリティが
違うので、今の決まりどおり撮影せずに止まる。

### CT

| ルーチン | シリーズ（種類・Series Description・画像数＝計算） | 合計 |
|----------|---------------------------------------------------|------|
| 頭部 単純 | 位置決め `Scout` 1／軸位 `AX 5mm` 30（150÷5）／軸位 `AX BONE 2.5mm` 60（150÷2.5）／線量 `Dose Report` 1 | 92 |
| 胸部 単純（既定） | 位置決め `Scout` 1／軸位 `Mediastinum 5mm` 60（300÷5）／軸位 `Lung 5mm` 60（300÷5）／軸位 `Lung 1mm` 300（300÷1）／冠状断 `COR 3mm` 83（250÷3）／線量 `Dose Report` 1 | 505 |
| 胸腹部骨盤 造影 | 位置決め `Scout` 1／軸位 `Ax Chest 2mm +C` 150（300÷2）／軸位 `Ax A/P 3mm +C` 133（400÷3）／冠状断 `Cor 3mm +C` 83（250÷3）／矢状断 `Sag 3mm +C` 116（350÷3）／線量 `Dose Report` 1 | 484 |
| 腹部骨盤 単純＋造影 | 位置決め `Scout` 1／軸位 `AX 5mm` 80（400÷5）／軸位 `AX 5mm +C` 80（400÷5）／冠状断 `COR 3mm +C` 83（250÷3）／矢状断 `SAG 3mm +C` 116（350÷3）／線量 `Dose Report` 1 | 361 |
| 肝臓 ダイナミック | 位置決め `Scout` 1／軸位 `AX 5mm` 50（250÷5）／軸位 `Arterial 3mm` 83／軸位 `Portal 3mm` 83／軸位 `Delayed 3mm` 83（各 250÷3）／冠状断 `COR Portal 3mm` 83（250÷3）／線量 `Dose Report` 1 | 384 |
| 冠動脈 CTA | 位置決め `Scout` 1／軸位 `Ca Score 3mm` 40（120÷3）／軸位 `CTA 0.5mm +C` 280（140÷0.5）／線量 `Dose Report` 1 | 322 |
| 腰椎 | 位置決め `Scout` 2（正面・側面）／軸位 `AX BONE 2mm` 75（150÷2）／矢状断 `SAG BONE 2mm` 30（60÷2）／冠状断 `COR BONE 2mm` 30（60÷2）／軸位 `AX SOFT 2mm` 75／矢状断 `SAG SOFT 2mm` 30／線量 `Dose Report` 1 | 243 |

CT のルーチンの `keywords`：頭部 単純「頭部」「HEAD」「BRAIN」、胸部 単純
「胸部」「CHEST」、胸腹部骨盤 造影「胸腹部」「CHEST ABDOMEN」、腹部骨盤 単純＋造影
「腹部」「ABDOMEN」、肝臓 ダイナミック「ダイナミック」「肝臓」「肝」「LIVER」、
冠動脈 CTA「CTA」「冠動脈」「心臓」「CORONARY」「CARDIAC」「HEART」、腰椎「腰椎」
「L-SPINE」「LUMBAR」「LSPINE」。「胸腹部」は「腹部」を含むが、長い語が勝つので
胸腹部骨盤になる。

腰椎の位置決めを2枚にしたのは推測で、資料で確かめていない（2方向の例は頭部の
資料にある。出典 3）。Series Description は英字にする（実際の装置の多くが英字で、
文字コードの組み合わせを増やさないため）。

### MR

ローカライザーは 3面×5枚（出典 26 の「1面 5〜8 枚」の下限）。MR の頭部の 2D は
出典 24 の 25 枚。ほかは「範囲 ÷（厚さ＋間隔）」で、厚さ・間隔は 3mm／0.3mm
（出典 26 の肩の値。膝は出典 29 の 3mm）。

| ルーチン | シリーズ（Series Description・画像数） | 合計 |
|----------|----------------------------------------|------|
| 頭部（既定） | `Localizer` 15（3面×5）／ `DWI b1000` 25／ `ADC` 25（計算した画像）／ `T2*` 25／ `T1 SAG` 25／ `T2 AX` 25／ `FLAIR` 25／ `TOF MRA` 116 | 281 |
| 腰椎 | `Localizer` 15／ `T1 SAG` 18（60÷3.3）／ `T2 SAG` 18（60÷3.3）／ `T2 AX` 45（150÷3.3） | 96 |
| 膝 | `Localizer` 15／ `PD FS SAG` 30（100÷3.3）／ `T2 FS COR` 30／ `PD FS AX` 30／ `T1 COR` 30 | 135 |
| 肩 | `Localizer` 15／ `T2 FS AX` 24（80÷3.3）／ `T2 FS COR` 24／ `T1 COR` 24／ `T1 SAG` 24 | 111 |

### CR・DX

方向は「CR・DX の撮影の方向」の標準の方向（追加の方向は入れない）。1方向 1枚。
CR は方向ごとに1シリーズ、DX は1シリーズに全部の方向を入れる。

| ルーチン | 方向 | 合計 |
|----------|------|------|
| 胸部（既定） | PA・側面 | 2 |
| 腹部 | AP（臥位）・PA（立位） | 2 |
| 腰椎 | AP・側面 | 2 |
| 頸椎 | AP・側面・開口 | 3 |
| 膝 | AP・側面 | 2 |
| 手 | PA・斜位・側面 | 3 |

### US

| ルーチン | 既定 | 合計 |
|----------|------|------|
| 腹部（既定） | 静止画 16（判定マニュアルが勧める下限。出典 36）・動画 0 | 16 |

甲状腺・乳腺・心エコーは、断面の数と動画の本数を資料の本文で確かめられなかった
ので付けない。US の画像を作る change で調べ直す。

## 既定のルーチンの当て方

撮影の画面を開いたとき（CLI では `-s`・`-i`・`--routine` を省いたとき）、DTG は
次の順でルーチンを1つ当てる。利用者が何も選ばなくても、そのルーチンで撮れる。

1. 予約の欄に、ルーチンの `keywords`（見出しの言葉）が含まれるかを、次の順に
   見る。先の欄で当たれば、後の欄は見ない（欄をまたいで語の長さは比べない）
   1. Requested Procedure Description
   2. Scheduled Procedure Step Description
   3. Body Part Examined (0018,0015)（RIS が返したときだけ）
2. 1つの欄でいくつかの語が当たれば、長い語のルーチンを選ぶ（「胸腹部」は
   「胸部」「腹部」より長いので、胸腹部骨盤のルーチンになる）。同じ長さなら、欄の
   中で前に出てくる語のルーチンにする（「頭部・胸部」なら頭部）
3. どの欄でも当たらなければ、予約のモダリティの既定のルーチン（`default: true`。
   CT は胸部 単純）

施設の検査のコードの対応表は持たない。照らす言葉は、DTG のルーチンの YAML の
`keywords` に持たせる。Body Part Examined は今の MWL の問い合わせで求めていない
ので、返却を求める値（[spec/12](../../../../docs/spec/12_modality_emulator.md) の 5.2）
に足す。MWL の標準の返却の値ではないので、返らない RIS が多いと見込み、返らなければ
検査名だけで当てる。

比べる前に、検査名と語の両方を Unicode の NFKC で正規化し、大文字と小文字を
区別しない形（casefold）にする。全角と半角、大文字と小文字は同じとみなし、語の
長さは正規化した後の文字数で数える。

当てる候補は、予約のモダリティ（Scheduled Procedure Step の Modality）と同じ
モダリティのルーチンだけ。予約のモダリティが空なら、テンプレートのモダリティを
使う（今の決まりも、空のモダリティを不一致として止めない）。緊急の患者（予約
なし）は、テンプレートのモダリティの既定のルーチンにする。次のときは、ルーチンの
読み込みの誤りにする：1つのモダリティに既定が2つ以上あるか1つも無い。同じ
モダリティの2つのルーチンに、正規化した後に同じになる語がある。付けるルーチンの
`keywords` は、日本語と英語の部位と検査の名前（例：胸部 単純は「胸部」「CHEST」、
肝臓 ダイナミックは「ダイナミック」も）にする。Body Part Examined の値（CHEST・
HEAD・ABDOMEN・LSPINE・HEART など。PS3.16 Annex L。出典 40）も英語の語で当たる。

## ルーチンの YAML

次は形を示す抜粋で、胸部 単純の6つのシリーズのうち4つだけを書いた。

```yaml
name: "ct_chest_plain"
label: "胸部 単純"
modality: "CT"
protocol_name: "CHEST ROUTINE"
default: true              # このモダリティの既定のルーチン（モダリティに1つだけ）
keywords: ["胸部", "CHEST"] # 見出しの言葉。予約の検査の記述と部位に照らす
series:
  - kind: "localizer"
    description: "Scout"
    images: 1
    views: ["frontal"]     # 画像ごとの方向。frontal（正面）か lateral（側面）。位置決めだけ
  - kind: "axial"
    description: "Mediastinum 5mm"
    images: 60
    slice_thickness: 5.0
  - kind: "coronal"
    description: "COR 3mm"
    images: 83
    slice_thickness: 3.0
  - kind: "dose_report"
    description: "Dose Report"
    images: 1
    series_number: null    # null は続きの番号。999 などを書ける
```

- CT の `kind` は `localizer`・`axial`・`coronal`・`sagittal`・`dose_report` の5つ。
  `images` はどのシリーズにも必ず書く（省けない）
- 位置決めの `views` は画像ごとの方向で、数は `images` と同じにする（腰椎の
  位置決めは `images: 2`・`views: ["frontal", "lateral"]`）。違えば読み込みの誤り。
  画面や CLI で位置決めの画像数を変えたときは、`views` を先頭から繰り返して
  割り当てる（2方向のまま 3 枚にすれば、正面・側面・正面）
- 軸位・冠状断・矢状断の `slice_thickness` は、Slice Thickness (0018,0050) と、
  画像の位置（Image Position (Patient)）の間隔の両方に使う（隙間の無い再構成）
- 造影のシリーズは `contrast: true`。`modality` がテンプレートと違えば、今の
  決まりと同じく撮影せずに止める
- 読み込みは装置のプロファイルと同じ形（`app/services/` のローダー、Pydantic の
  検証、名前は英数字・`_`・`-` のファイル名だけ）
- MR・CR・DX・US のルーチンは、`series` の持つ値がモダリティごとに違う（「ルーチンの
  形」）。MR は `kind`（`localizer`・`acquisition`・`derived`）・`plane`・
  `slice_thickness`・`spacing`、CR・DX は `views`（方向の並び）、US は
  `still_images`・`clips`・`frames_per_clip`。`modality` で検証の形を選ぶ

## DICOM の値（CT）

種類ごとに、次の値を変える。ほかの値（患者・Study・装置）は今のまま。Frame of
Reference UID は、線量の画面を除き、1回の撮影のすべてのシリーズで同じにする
（同じ寝台の位置で撮った画像なので）。

| 種類 | SOP Class | Image Type | Image Orientation (Patient) | ほか |
|------|-----------|------------|-----------------------------|------|
| 位置決め | CT Image Storage | `ORIGINAL\PRIMARY\LOCALIZER` | 正面 `1\0\0\0\0\-1`、側面 `0\1\0\0\0\-1` | 投影の画像に見える画素 |
| 軸位 | CT Image Storage | `ORIGINAL\PRIMARY\AXIAL`（今と同じ） | `1\0\0\0\1\0` | |
| 冠状断・矢状断 | CT Image Storage | `DERIVED\SECONDARY\AXIAL` | 冠状断 `1\0\0\0\0\-1`、矢状断 `0\1\0\0\0\-1` | Image Position (Patient) は向きに合わせて進める |
| 線量の画面 | Secondary Capture Image Storage（1.2.840.10008.5.1.4.1.1.7） | `DERIVED\SECONDARY` | 無し | 下の「線量の画面の属性」 |

すべての種類に共通の値：

- Series Description (0008,103E)：ルーチンの `description`
- Series Number (0020,0011)：今の決まりは、予約で撮った累計のシリーズ数の次の
  番号（`exam_records.series_count`）で、使った番号そのものは記録しない。番号を
  書けるようにすると、初回が `1,2,3,999` のとき累計は 4 で、追加撮影の自動の
  番号が 5 になり、書いた番号と自動の番号がぶつかりうる。そこで次のように変える
  - 予約ごとに、使ったシリーズ番号を記録する（撮影の記録に列を足す。前の版の
    記録は `1`〜`series_count` を使ったものとして移す）
  - 記録には、番号ごとに、自動で付けたか、ルーチンに書いた番号かを残す
  - 自動の番号は、自動で付けた番号の最大の次にする。その番号が使った番号（書いた
    番号を含む）なら、空いている番号まで1つずつ進める。初回が `1,2,3,501` なら、
    次の自動の番号は 4 になる
  - 書いた番号が、使った番号か、同じ撮影のほかのシリーズの番号と同じなら、
    撮影せずに止める
- Protocol Name (0018,1030)：ルーチンの `protocol_name`。今の MPPS は画像の
  Protocol Name を読み、Performed Series Sequence の中の Protocol Name に入れる
  （Performed Protocol Code Sequence は空のまま）。ルーチンの値もそこに入る
- 造影のシリーズ：Contrast/Bolus Agent (0018,0010) を入れる（Contrast/Bolus
  Module は造影を使ったときに要る。PS3.3 C.7.6.4）
- Image Type の Value 4（会社ごとの値）は付けない。Source Image Sequence も
  付けない（Type 3）
- RDSR は作らない（proposal の「承認者が決めること」の 1）

### 線量の画面の属性

Secondary Capture Image IOD（PS3.3 A.8.1）で、CT の画像と違うところを並べる。

- Modality (0008,0060) は `CT`（装置が作った画面なので。出典 1 の GE・Siemens の
  例も CT のシリーズ）
- SC Equipment Module：Conversion Type (0008,0064) は `WSD`（PS3.3 C.8.6.1）
- General Image Module：Patient Orientation (0020,0020) は空の値で出す（Type 2C。
  Image Orientation (Patient) を持たない画像で要る。人体の向きの無い画面なので
  空にする。PS3.3 C.7.6.1）
- Frame of Reference・Image Plane の属性（Image Position・Image Orientation・
  Slice Location・Slice Thickness）と CT Image Module の属性（KVP・Rescale など）は
  出さない
- 画素は 8 ビットの MONOCHROME2（Bits Allocated 8・Bits Stored 8・Pixel
  Representation 0）。架空の CTDIvol・DLP の表を文字で描く（今の `simple_text` の
  画素の作り方を使う）
- 試験では、上の属性があることと、CT の画像の属性が無いことを確かめる

## 画面と CLI

- 撮影の設定の「テンプレート」の隣に「ルーチン [胸部 単純 ▼]」。開いたときには
  「既定のルーチンの当て方」で当てたルーチンが選ばれている。並べるのは、予約の
  モダリティと同じルーチンと、最後の「手で入れる」
- ルーチンが選ばれているときは、「シリーズ数」「画像数」の代わりに、シリーズの行
  （番号・Series Description・種類・画像数の入力欄・外すボタン）を出す。画像数の
  欄にはルーチンの既定が入っている
- 「手で入れる」を選ぶと、今の「シリーズ数」「画像数」の欄になる
- 合計の画像数の上限（10.5）はルーチンでも同じ
- CLI：`-s`・`-i`・`--routine` を省けば、当てたルーチンで撮る。結果の表示と
  `--json` に、使ったルーチンの名前を出す。`--routine ct_chest_plain` で選べ、
  画像数を変えるときは `--routine-images 1,60,60,300,83,1`（並びの数と同じ数）。
  `-s`・`-i` を指定すれば今の手入力と同じで、`--routine` と同時に指定したら終了
  コード 4

## 試験

- ルーチンの YAML の読み込みと検証（種類・画像数・`modality`・名前の形。
  画像数の無いシリーズ、モダリティに既定が1つでないことは読み込みの誤り）
- 付けたすべてのルーチン（CT・MR・CR・DX・US）の画像数が、上の表の値と同じこと
- 当て方：検査の記述の見出しの言葉で当たる（長い語が勝つ、先の欄が勝つ）、
  Body Part Examined で当たる、当たらなければ既定、緊急の患者はテンプレートの
  モダリティの既定
- 種類ごとの Image Type・Image Orientation (Patient)・SOP Class・Series
  Description・Series Number
- 線量の画面が Secondary Capture の必須の属性を持つこと（pydicom で読み、
  dciodvfy があれば流す）
- 追加撮影で `series_number` がぶつかったら止まること
- 「手で入れる」の撮影が今と同じ画像になること

## 出典

本文を Defuddle か WebFetch で取得して読んだものは「読んだ」、検索の結果の要約
だけのものは「要約だけ」と書く。

| # | 資料 | URL | 読み方 |
|---|------|-----|--------|
| 1 | Clunie, CT の線量の情報の取り出し（2010） | <https://dclunie.com/papers/D2_0800_Clunie_RadiationDose.pdf> | 読んだ |
| 2 | DICOM FAQ, CT Dose Information in DICOM Data | <https://dicom.nema.org/documents/CT_Dose_Information_in_DICOM_Data-DICOM_FAQ.pdf> | 読んだ |
| 3 | AAPM, Adult Routine Head CT Protocols | <https://www.aapm.org/pubs/ctprotocols/documents/adultroutineheadct.pdf> | 読んだ |
| 4 | AAPM, Adult Routine Chest CT Protocols | <https://aapm.org/pubs/CTProtocols/documents/AdultRoutineChestCT.pdf> | 読んだ |
| 5 | Radiology of Indiana, CT Protocols | <https://www.radiologyofindiana.com/wp-content/uploads/2025/12/CT-Protocols-ROI.pdf> | 読んだ |
| 6 | Radiopaedia, CT chest abdomen-pelvis (protocol) | <https://radiopaedia.org/articles/ct-chest-abdomen-pelvis-protocol-2?lang=us> | 読んだ |
| 7 | 東芝の CT の患者のプロトコルを Secondary Capture で出す例 | <https://physik.gesundheitsverbund.at/ct/ma_min.htm> | 読んだ |
| 8 | Siemens Healthineers Academy, Patient Protocol の自動送信の設定 | <https://academy.siemens-healthineers.com/en-us/how-to-configure-auto-send-patient-protocol-page> | 要約だけ |
| 9 | 3D Slicer の掲示板、軸位に位置決めが混ざる例（血管撮影） | <https://discourse.slicer.org/t/dicom-import-problem-related-to-localizer-images/4730> | 読んだ |
| 10 | DICOM PS3.3 C.8.2 CT Modules | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.2.html> | 読んだ |
| 11 | Radiopaedia, CT abdomen-pelvis (protocol) | <https://radiopaedia.org/articles/ct-abdomen-pelvis-protocol-1?lang=us> | 読んだ |
| 12 | 日本医学放射線学会, 画像診断ガイドライン 2021 年版（肝） | <https://www.radiology.jp/content/files/gl2021/gl_2021_05.pdf> | 読んだ |
| 13 | AAPM, Adult Tri-phasic Liver (HCC) | <https://www.aapm.org/pubs/CTProtocols/documents/Adult_Tri-phasic_Liver_HCC_AAPM_format_Clean.pdf> | 読んだ |
| 14 | Radiopaedia, Coronary CT angiography (protocol) | <https://radiopaedia.org/articles/coronary-ct-angiography-protocol?lang=us> | 読んだ |
| 15 | 石灰化スコアと CTA の撮影の条件の表（Medicina, 2023） | <https://pmc.ncbi.nlm.nih.gov/articles/PMC10384118/table/medicina-59-01223-t003> | 要約だけ |
| 16 | Investigating the CT localizer radiograph（PMC） | <https://pmc.ncbi.nlm.nih.gov/articles/PMC4651250/> | 読んだ |
| 21 | O'Connell, 線量の画面の会社ごとの違い（RSNA のポスター） | <https://www.rsna.org/uploadedFiles/RSNA/Content/Science_and_Education/Quality/3062-OConnell.pdf> | 読んだ |
| 22 | Siemens, CT の DICOM Conformance Statement（2008） | <https://marketing.webassets.siemens-healthineers.com/1800000000073752/6cb79c83fa89/2008a_ct_dicomconformancestatement-00073752_1800000000073752.pdf> | 読んだ |
| 23 | OpenREM, DICOM のファイルからの取り込み | <https://docs.openrem.org/en/latest/import-from-file.html> | 読んだ |
| 24 | Canon Medical, Vantage Elan の MR Stroke Protocol | <https://br.medical.canon/products/magnetic-resonance-imaging/download-protcols/vantage-elan/> | 読んだ |
| 25 | OHSU, MR Stroke Brain WO Neuro Protocol | <https://ohsu.edu/school-of-medicine/diagnostic-radiology/mr-stroke-brain-wo-neuro-protocol> | 読んだ |
| 26 | MCR, MSK MRI Protocols（肩などのローカライザーと厚さ） | <https://mcrrads.com/wp-content/uploads/2025/10/mcr-msk-protocols-feb-23.pdf> | 読んだ |
| 27 | UCSD CFMRI, Siemens Prisma のデータの転送（シリーズの並びの例） | <https://ucsd-center-for-functional-mri-cfmri-prisma-external.readthedocs-hosted.com/en/latest/transfer.html> | 読んだ |
| 28 | Radiopaedia, Lumbar spine protocol (MRI) | <https://radiopaedia.org/articles/147093> | 読んだ |
| 29 | Radiopaedia, Knee protocol (MRI) | <https://radiopaedia.org/articles/68261> | 読んだ |
| 30 | DICOM PS3.17 EEEE.4（ADC の Image Type の例） | <https://dicom.nema.org/medical/dicom/2024c/output/chtml/part17/sect_EEEE.4.html> | 読んだ |
| 31 | Radiopaedia, Chest radiograph | <https://radiopaedia.org/articles/chest-radiograph?lang=us> | 読んだ |
| 32 | Radiopaedia, Lumbar spine series | <https://radiopaedia.org/articles/lumbar-spine-series?lang=gb> | 読んだ |
| 33 | Radiopaedia, Knee series | <https://radiopaedia.org/articles/knee-series?lang=us> | 読んだ |
| 34 | DICOM PS3.3 C.8.1 CR Modules | <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.html> | 読んだ |
| 35 | DICOM PS3.3 C.8.11.5 DX Positioning Module | <https://dicom.nema.org/medical/dicom/2024c/output/chtml/part03/sect_C.8.11.5.html> | 読んだ |
| 36 | 丸山ほか, 腹部超音波検査における記録断面数の増加が検査時間に及ぼす影響（日本消化器がん検診学会雑誌, 2019） | <https://www.jstage.jst.go.jp/article/jsgcs/57/2/57_170/_article/-char/ja> | 抄録を読んだ |
| 37 | Radiopaedia, Abdominal radiography | <https://radiopaedia.org/articles/abdominal-radiograph?lang=us> | 読んだ |
| 38 | Radiopaedia, Cervical spine series | <https://radiopaedia.org/articles/cervical-spine-series?lang=us> | 読んだ |
| 39 | Radiopaedia, Hand series | <https://radiopaedia.org/articles/hand-series?lang=us> | 読んだ |
| 40 | DICOM PS3.16 Annex L（Body Part Examined の定義の語） | <https://dicom.nema.org/medical/dicom/current/output/chtml/part16/chapter_L.html> | 読んだ |

次の頁は読めなかったので、上の表に使っていない：Gundersen Health の CT と膝の
プロトコル（403）、Austin Radiological の Adult Body Protocols（接続を拒否）、
Dartmouth の Body CT protocols（404）、ACVR の頁（404）、NLST の辞書（ログインが
要る）、ADNI3 の Siemens のプロトコル（名前を引けない）、British Society of
Echocardiography の最小のデータセット（PDF を読めない）、甲状腺の超音波の
プロトコル（PDF を読めない）。
