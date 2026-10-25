# ADR-0029: CT の線量の報告は、線量の画面のほかに X-Ray Radiation Dose SR のシリーズでも作れる

- 状態：採用
- 作成日：2026-10-25
- 最終更新日：2026-10-25

## 背景

[ADR-0025](0025-exam-routines.md) は CT の最後のシリーズ「Dose Report」を、装置の
画面を写した Secondary Capture の画像（Modality は `CT`）で作る。実際の CT の検査では、
この画面のほかに、同じ検査の中に Modality が `SR` の線量の報告（RDSR）のシリーズが
入る。PACS の表示・検索・シリーズの一覧に、画像でない SR のシリーズが混ざった検査を
試すには、これも作れる必要がある。

## 決定

1. 線量の報告のシリーズの種類に `dose_sr` を足す。Modality は `SR`、SOP Class は
   X-Ray Radiation Dose SR Storage（1.2.840.10008.5.1.4.1.1.88.67）。既存の
   `dose_report`（Secondary Capture）は変えない
2. SR の内容は PS3.16 の TID 10011「CT Radiation Dose」の最小の形にする。必須（M）の行
   と、条件を満たして必須になる（MC）行だけを作る。根は X-Ray Radiation Dose Report
   (113701, DCM)、Procedure reported は Computed Tomography X-Ray、観察の文脈は
   装置（Device Observer UID）と撮影の開始・終了の日時、蓄積の範囲は Study（その
   Study Instance UID つき）。TID 10012 の蓄積（撮影の数と DLP の合計）と、撮影ごとの
   TID 10013 を持つ
3. 撮影（TID 10013）は、そのシリーズの位置決め（Stationary Acquisition）と軸位
   （Spiral Acquisition）を1つずつ。数値は線量の画面と同じ架空の CTDIvol と DLP、
   撮影の長さは 画像数 × 画像の間隔。線量の画面と SR の合計は一致する。撮影条件
   （管電圧・管電流・コリメーションなど）は定数の架空の値で、軸位だけが Pitch Factor と
   Exposed Range を持つ（それぞれ Spiral のとき必須）。撮影の Irradiation Event UID は
   撮影ごとに作る
4. SR Document の各モジュール（PS3.3 A.35.8）を持ち、画素・Frame of Reference は持たない。
   Enhanced General Equipment の Device Serial Number (Type 1) は、テンプレートと装置の
   プロファイルが決めなければ既定の値を入れる。装置のプロファイルが足した画像の属性は
   外す
5. 撮影のとき、`dose_report`（画面 `screen`・SR `sr`・両方 `both`）で選ぶ。`sr` はルーチンの
   線量の画面の行（シリーズ番号を含む）を SR に替え、`both` は画面の次に SR の行を足す。
   撮らない行には何もしない。CT 以外と手で入れたシリーズには使わない。画面は「線量の
   報告（CT）」の選択、CLI は `exam --dose-report`。SR を撮るときは、撮影になる
   位置決めか軸位のシリーズも撮る
6. MPPS の Performed Series Sequence では、SR を Referenced Non-Image Composite SOP
   Instance Sequence に入れる（画像は Referenced Image Sequence のまま。PS3.4 の表 F.7.2-1）
7. 既定は `screen`（今までの検査の枚数・シリーズの数は変わらない）。`both` を既定に
   する案は、PR で承認者の判断を求める

## 検討した選択肢

- 線量の画面の行を常に SR に替える：実際の装置に近いが、今までの検査（画面の画像）と
  シリーズ・枚数が変わり、画面を見る試験ができなくなる
- ルーチンの YAML に画面と SR の両方の行を書き、利用者が行を外して選ぶ：選択肢が
  ルーチンごとに増える。画面は「外す」しか無く、SR を後から足せない
- RDSR に撮影ごとの詳細（再構成、造影、SSDE、被ばく線量の推定）を全部入れる：実際の
  RDSR に近づくが、必須でない行は PACS の表示・送信の試験の価値が小さい

## 結果

- CT の検査の中に SR のシリーズを含められる。ModalitiesInStudy は `CT\SR` になる
- 線量の値は架空で、実際の線量の確かめには使えない
- SR の内容の木は、dicom-validator（規格 2026d の IOD の確認）では検査されない。木の
  構造は試験で TID 10011・10012・10013 の必須の行を確かめる

## 決めないこと

- 投影 X 線（TID 10001）、Enhanced X-Ray Radiation Dose SR、Radiopharmaceutical
  Radiation Dose SR
- 撮影ごとの Target Region の使い分け（今は Entire body）

## 出典

- PS3.3 A.35.8（X-Ray Radiation Dose SR IOD）、C.17.1〜C.17.3、C.7.5.2
- PS3.16 TID 10011・10012・10013・10014・1002・1004、CID 4030・4031・4053・10000・10001・
  10013・10021
- PS3.4 B.5、F.7.2

## 関連

- [ADR-0025](0025-exam-routines.md)：撮影のルーチンと線量の画面
- [ADR-0028](0028-mr-images.md)：シリーズのモダリティ
