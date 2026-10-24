# Spec Delta

## ADDED Requirements

### Requirement: 緊急の患者の追加撮影は前の撮影と同じ Study と患者にする

緊急の患者（予約なし）の追加撮影は、前の緊急の撮影の Study Instance UID を指定したときだけ
受けなければならない（SHALL）。DTG は、書き終えた緊急の撮影の Study Instance UID・Study ID・
患者の値を記録し、追加撮影ではその記録の Study Instance UID・Study ID・患者の値を使う。
指定した患者ID か氏名が記録と違えば、撮らずに断る（SHALL）。受付番号は空のままにし、
シリーズは新しい Series Instance UID で作る。Study の日時・説明と Series Number は、予約の
追加撮影と同じ決まりにする。MPPS を使うときは、新しい MPPS の SOP Instance で N-CREATE と
N-SET を送る（IHE PIR の Case 6 を試すため）。

#### Scenario: 緊急の撮影に追加で撮る

- **WHEN** 緊急の患者 `E1` で撮影し（Study Instance UID は `2.25.1`）、`exam --emergency --append --study-uid 2.25.1` を同じ患者ID と氏名で実行する
- **THEN** 追加撮影の画像の Study Instance UID は `2.25.1`、Study ID と患者の値は1回目と同じ、受付番号は空で、Series Number は1回目の続きになる

#### Scenario: 患者ID が違う

- **WHEN** `--study-uid 2.25.1` に、1回目と違う患者ID で追加撮影を指定する
- **THEN** 撮らずに断り、画像・記録・MPPS は作られない

#### Scenario: Study Instance UID を指定しない

- **WHEN** 撮影の画面で、緊急の患者に追加撮影を指定する（画面には Study Instance UID を指定する欄が無い）
- **THEN** 撮らずに「緊急の患者（予約なし）では追加撮影はできません」と断る。CLI で `--study-uid` を省いた `exam --emergency --append` は、終了コード 2 で断る
