# ADR-0030: PET/CT の検査は、同じ Study に CT と PT のシリーズを入れて作る

- 状態：採用
- 作成日：2026-10-25
- 最終更新日：2026-10-25

## 背景

PET/CT の検査は、1つの Study に CT のシリーズと PT のシリーズが入る。PACS では、
検査の Modality が `PT\CT` や `CT\PT` と表示される。[ADR-0028](0028-mr-images.md) で
シリーズごとにモダリティを持てるようになったが、PT の画像（PET Image Storage）と、
CT と PT が混ざった検査の作り方は無かった。

## 決定

1. テンプレート `petct_generic` を足す。テンプレートのモダリティは `PT`（予約の
   Scheduled Procedure Step の Modality と合わせる）。SOP Class は PET Image Storage
   （1.2.840.10008.5.1.4.1.1.128）。テンプレートの `ct_image` は、同じ検査の CT の
   シリーズに当てる
2. シリーズの種類に `pet_ac`（減弱補正あり）・`pet_nac`（補正なし）を足す。PT のシリーズ
   だけが持つ。ルーチンは `modality: PT` の形で、行ごとに `modality`（CT か PT）と `kind`
   を書く。CT の行の種類は CT のルーチンと同じ（位置決め・軸位・線量の画面。
   [ADR-0029](0029-dose-report-sr.md) の線量の報告の SR にも替えられる）。CT のシリーズは
   CT Image Storage、PT のシリーズは PET Image Storage で作る
3. PET Image は PS3.3 A.21 の必須のモジュールを持つ。PET Series（Units は `BQML`、Series
   Type は `WHOLE BODY\IMAGE`、Corrected Image、Decay Correction `START`）・PET
   Isotope（F-18 FDG。コードは CID 4020・4021 の SCT の値）・NM/PET Patient Orientation
   （Type 2 を空で）・PET Image（Rescale Intercept 0、Frame Reference Time、Image
   Index、Decay Factor など）を、架空の値で入れる。Corrected Image は、補正ありは
   `DECY\ATTN\SCAT\DTIM\RAN\NORM`、補正なしは `ATTN`・`SCAT` を除く
4. 画素は 16 ビット符号なし（Bits Allocated = Bits Stored = 16）。行列は 128×128、視野は
   700 mm（架空）で、ジョブの画素の大きさには従わない。CT のシリーズは今までの大きさ
5. CT と PT は同じ Study Instance UID と Frame of Reference UID を使い、軸位は同じ
   z 軸で進める。Image Type は `ORIGINAL\PRIMARY`
6. ルーチンを2つ足す：`pt_whole_body`（既定。Topogram・CT・PET AC・PET NAC・線量の画面の
   順に撮る）と `pt_whole_body_pet_first`（PT を先に撮る並び）。PACS が検査の Modality を
   最初に届いたシリーズの順に並べるとき、`PT\CT` と `CT\PT` の両方を作れる。ファイル名の
   順（＝送る順）はシリーズの順と同じ
7. 装置のプロファイルが作れる SOP Class に PET Image Storage を足し、例として
   `dtg_synthetic_petct` を置く（CT のシリーズにも同じプロファイルを重ねる）
8. 線量の報告の SR は、同じ検査の CT の撮影（位置決めと軸位）だけを載せる。PET は撮影に入れない

## 検討した選択肢

- CT のテンプレートに PT のシリーズを足す：テンプレートの Modality は予約と合わせる決まり
  （ADR-0028）で、PT の予約（PET/CT は `PT` で予約されることが多い）を CT のテンプレートで
  撮れない
- 予約のモダリティを `CT\PT` のような複数値にする：Scheduled Procedure Step の Modality
  (0008,0060) は 1 値（VM 1）。ModalitiesInStudy (0008,0061) は PACS が検査のシリーズから
  作る値で、画像には入れない
- PET の画素を CT と同じ 512 にする：実際の PET の行列に合わず、枚数の多い検査のディスクを
  使いすぎる

## 結果

- PET/CT の予約と緊急の患者を、画面と CLI の両方で撮れる（緊急の患者はテンプレートに
  `petct_generic`）。全身の標準の撮影は 5 シリーズ・935 枚（CT 333・PET 300×2・
  Topogram 1・線量の画面 1）
- PT の値は架空で、定量（SUV など）の確かめには使えない

## 決めないこと

- 融合画像（Secondary Capture や Enhanced PET）、PET の動態・同期・MIP の投影
- 患者の体重・投与量から SUV を計算する値（Patient Weight は予約・Job の値のまま）
- CT の予約（Modality が `CT`）に PET を足す撮影

## 出典

- PS3.3 A.21（PET Image IOD）、C.8.9.1・C.8.9.2・C.8.9.4、C.8.4.6
- PS3.16 CID 4020・4021（放射性核種・放射性医薬品）
- PS3.4 B.5

## 関連

- [ADR-0028](0028-mr-images.md)：シリーズのモダリティ
- [ADR-0029](0029-dose-report-sr.md)：線量の報告の SR
