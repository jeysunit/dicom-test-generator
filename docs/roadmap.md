# ロードマップ

未確認・未実装・未決定のものを並べる。実装したら spec に移し、ここから削除する。
範囲に入れないと決めたものは [project_charter.md](project_charter.md) の 4 章に
ある。

## 1. 未確認のもの

- **Orthanc を相手にした保管確認（Storage Commitment）。** 実装とテスト（スタブを相手にしたもの）は
  済んでいる。Orthanc を相手に、送信キューの「保管の確認」が「確認済」になることを
  手動で確認していない。手順は [usage.md](usage.md) の
  「Orthanc で保管確認をテストする」にある
- **作成の性能。** 目標として、1画像の作成を 100ms 未満（UID の生成 1ms 未満、
  簡易モードのピクセル 10ms 未満、CT モードのピクセル 50ms 未満、Dataset の構築
  50ms 未満）に置いていたが、測定していない

## 2. 次に行うもの

- **イメージの最初の公開。** 公開の workflow（`v` で始まるタグの push と手動の
  実行のときに GHCR に公開する）は用意したが、タグはまだ push していない。公開するまでは、
  README の `docker pull` は失敗し、[usage.md](usage.md) の 1.2 のとおりイメージを
  ビルドして使う。公開の後に、GHCR のパッケージが公開になっていることを確認する

## 3. 未実装のもの

| 項目 | 現在の状態 | 関係するドキュメント |
|------|------------|----------------------|
| Web 画面でのファイルの作成（Job YAML や `quick` に相当する画面） | ファイルの作成は CLI の `generate`・`quick` で行う。Web 画面は撮影だけを持つ | [ADR-0022](decisions/0022-remove-desktop-gui.md) |
| CT 以外のモダリティ（MR・CR・DX・US など） | 作成できる SOP Class は CT Image Storage だけ | [spec/13](spec/13_device_profiles.md) の 4.3 |
| 装置プロファイルの `uid`・`pixel`・`series` フィールド | モデルにフィールドが無く、書くと検証エラーになる | [spec/13](spec/13_device_profiles.md) の 3.1・11 章 |
| 装置プロファイルの `worklist` フィールド | 予約の値の転記方法はプロファイルで変えられない | [spec/13](spec/13_device_profiles.md) の 8 章 |
| 装置プロファイルの `services.modality_worklist` | 値を持つだけで、動作に反映されない | [spec/13](spec/13_device_profiles.md) の 3.1 |
| 表現できない文字を `?` に置き換えて撮影する異常のデータ | 表現できない文字があれば必ず停止する | [ADR-0018](decisions/0018-stop-on-unrepresentable-characters.md) |
| 色と文字の値（デザイントークン）を1か所のファイルで管理する | 入力の CSS に値を書き、テストで表と比較している | [spec/12a](spec/12a_web_screens_and_cli.md) の 10.1 |
| Job とテンプレートの、受け付けるが作成に使わない項目（`pixel_spec.background_color`・`text_color`・`font_size`、`abnormal.invalid_sop_uid_probability`、`transfer_syntax` の `uid` 以外、`patient.age`・`patient_comments`、`study.num_series`、テンプレートの `spatial`・`ct_image.rescale_*`・`window_presets`・`file_meta.transfer_syntax_uid`、病院テンプレートの `use_alphabetic`） | 検証はするが、画像には反映しない | [spec/03](spec/03_data_models.md)・[spec/06](spec/06_dicom_rules.md)・[spec/07](spec/07_job_schema.md) |
| 例外 `JobSchemaError`・`JobValidationError` | 定義だけで、送出する箇所が無い | [spec/08](spec/08_error_handling.md) |

## 4. 未決定のもの

- 今は無い。ダークテーマで文字・フォーカスリングに使う色は、`--color-link`（`#a5a8ff`）
  に決めた（[spec/12a](spec/12a_web_screens_and_cli.md) の 10.2）
