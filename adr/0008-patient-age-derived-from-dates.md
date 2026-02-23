# ADR-0008: PatientAge を birth_date / study_date から算出する

## ステータス

**Accepted** - 2026-02-23

## 背景

従来実装では `patient.age` をそのまま `(0010,1010) PatientAge` に設定していたため、
以下の不整合が発生し得た。

1. `birth_date` と `study_date` に対して `age` が矛盾していても生成できる
2. `study_date < birth_date` の不正データでも生成できる
3. モダリティ相当のダミーデータとして期待される「検査日時点の年齢」と一致しない

## 決定

`PatientAge` は **常に** `birth_date` と `study_date` から **日本法基準**（年齢計算ニ関スル法律 + 民法143条）で自動算出する。
`patient.age` は互換入力として保持するが、DICOM出力値の決定には使わない。

併せて、`study_date >= birth_date` を必須バリデーションとする。

## 実装方針

- `GenerationConfig` のモデルバリデーションで日付整合性を検証
  - `birth_date` / `study_date` が暦日として有効
  - `study_date < birth_date` はバリデーションエラー
- `DICOMBuilder._calculate_patient_age` で日本法準拠の年齢算出
  - 加齢日 = 誕生日の前日のN年後（民法143条）
  - 2/29生まれは閏年・非閏年とも2/28に加齢
  - DICOM AS 範囲 (0-999) チェック

## 影響

### 良い点

- 出力DICOMの `PatientAge` が検査日時点の値と一致する
- 日付矛盾を早期に検出できる
- モダリティダミー用途での整合性が向上する

### 悪い点

- `patient.age` に任意値を入れて異常データを作る使い方はできなくなる
  - 異常データは `abnormal` 設定など別機構で表現する

## 関連する決定

- [spec/03_data_models.md](../spec/03_data_models.md)
- [spec/06_dicom_rules.md](../spec/06_dicom_rules.md)
- [spec/07_job_schema.md](../spec/07_job_schema.md)
