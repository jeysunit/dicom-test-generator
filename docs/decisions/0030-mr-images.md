# ADR-0030: MR の画像は、シリーズのモダリティで MR Image Storage として作る

- 状態：採用
- 作成日：2026-10-25
- 最終更新日：2026-10-27

## 背景

撮影の画面と CLI の `exam` が作れる画像は CT だけだった。[ADR-0025](0025-exam-routines.md)
は MR のルーチン（シリーズの並びと画像数）を持つが、MR の画像の作り方を「決めない
こと」にしていた。そのため、MR の予約（Modality が MR）を選ぶと「予約は MR、
テンプレートは CT です」と表示して撮影できず、緊急の患者もテンプレートが CT の
1つしか無かった。PACS の表示や送信の試験には、CT のほかに MR の検査が要る。

## 決定

1. シリーズに `modality` を持たせる。`None` はテンプレートのモダリティで、今までの
   Job と手入力は CT のまま動く。画像は `modality` が MR のシリーズだけ MR Image
   Storage（1.2.840.10008.5.1.4.1.1.4）で作る。MR のシリーズの種類は、位置決め
   （`localizer`）・撮像（`acquisition`）・計算で作った画像（`derived`）の3つ
2. MR の画像は PS3.3 A.4 の必須のモジュール（Patient・General Study・General Series・
   Frame of Reference・General Equipment・General Image・Image Plane・Image Pixel・MR
   Image・SOP Common）を持つ。MR Image Module の Type 1・Type 2（Scanning Sequence・
   Sequence Variant・Scan Options・MR Acquisition Type・Echo Time・Echo Train Length）
   と、Type 2C の Repetition Time・Inversion Time は、規格どおりに必ず入れる
3. Scanning Sequence と MR Acquisition Type はルーチンのシリーズの `sequence`
   （SE・IR・GR・EP。既定 SE）と `acquisition_type`（2D・3D。既定 2D）で決める。
   Sequence Variant・Repetition Time・Echo Time・Echo Train Length・Inversion Time
   は、`sequence` ごとに1組の架空の値を持つ。シリーズごとの細かい撮像条件は持たない
4. 画素は Bits Allocated 16・符号なし・MONOCHROME2。画素間隔は、視野（架空の
   240 mm）を画素数で割った値にする。断面（axial・sagittal・coronal）は CT の
   断面と同じ向きと軸で進め、三方向の位置決め（`three_plane`）は画像を3等分して
   順に axial・coronal・sagittal にする。画像の間隔は スライス厚 + ルーチンの
   `spacing`（すきま）
5. モダリティのテンプレートに `mr_generic` を足す。装置のプロファイルが作れる
   SOP Class に MR Image Storage を足し、例として `dtg_synthetic_mr` を置く
6. 撮影でテンプレートを指定しないときは、予約のモダリティに合うテンプレートで撮る
   （設定の既定のテンプレートが合えばそれ、無ければ名前の順で最初に合うもの）。
   設定の既定の装置のプロファイルがそのモダリティと違えば重ねない。テンプレートや
   プロファイルを明示したときは今までどおり、モダリティが違えば撮影しない。
   緊急の患者は、画面のテンプレートと CLI の `-m` で `mr_generic` を選ぶ

## 検討した選択肢

- Enhanced MR Image Storage（複数フレーム）：1ファイルに全スライスが入り、PACS の
  取り込みの試験には別の価値がある。ただし ADR-0025 のルーチンが1スライス1ファイル
  の並びで、実際の検査もこの形が多い。複数フレームは別の決定にする
- 撮像条件をシリーズごとに YAML へ全部書く：実際の装置に近づくが、書く量が増える。
  PACS の表示や送信の試験に要るのは、Type 1・2 が正しく入っていること
- 予約のモダリティと違うテンプレートの撮影を許す：Modality と SOP Class が予約と
  食い違う検査ができる。食い違いは異常のデータの仕事にする

## 結果

- MR の予約と緊急の患者を、画面と CLI の両方で撮れる。ルーチンの MR（頭部・
  腰椎・膝・肩）の並びと枚数のとおりの検査ができる
- シリーズに `modality`・`plane`・`sequence`・`acquisition_type` が増える
- MR の画像の値は架空で、実際の撮像の確かめには使えない

## 決めないこと

- CR・DX・US の画像の作り方（ADR-0025 のまま）
- 拡散強調の b 値・テンソル、造影の動態、心電同期などの MR の追加の属性

## 出典

- PS3.3 A.4（MR Image IOD）、C.8.3.1（MR Image Module）、C.7.6.2（Image Plane Module）
- PS3.4 B.5（標準の SOP Class）

## 関連

- [ADR-0025](0025-exam-routines.md)：撮影のルーチン
- [spec/03](../spec/03_data_models.md)・[spec/06](../spec/06_dicom_rules.md)・
  [spec/13](../spec/13_device_profiles.md)
