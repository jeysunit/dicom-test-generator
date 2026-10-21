# ADR-0016: 公開のテンプレートと例のプロファイルに商用の製品の名前を使わない

- 状態：採用
- 日付：2026-10-18
- 作成日：2026-10-22

## 背景

CT のモダリティのテンプレートは、名前と中身（`manufacturer`・
`manufacturers_model_name`・`station_name` など）に実在の製品の名前を
使っていた。このリポジトリは公開しているので、作った画像が実在の製品の出力と
誤解されるおそれがある。

## 決定

1. **テンプレートの名前は一般の名前にし、商用の製品の名前・会社の名前を
   使わない。** 形は `<モダリティ>_<部位や用途>_<番号や特徴>`（小文字・`_`
   区切り）。例：`ct_generic`・`ct_chest_5mm`・`mr_head_generic`
2. **公開のテンプレートと、公開の例のプロファイル（`profiles/examples/`）の
   名前・`manufacturer`・`manufacturers_model_name`・`station_name` に
   商用の名前を書かない。** `DTG Synthetic CT` のような架空の名前にする
3. **実在の装置に寄せたいときは、装置のプロファイルにする**
   （[ADR-0012](0012-device-profiles.md)）。リポジトリの外の置き場の
   プロファイルには、この決まりを当てない
4. **古い名前を読みに来た Job YAML・CLI には、プロファイルの置き場へ案内する
   エラーを出す。** `TemplateNotFoundError` の `hint` に案内を入れ、別名として
   黙って読まない。古い名前は商用の名前を含むので、コードには名前そのものでなく
   SHA-256 の値で持つ（`app/services/template_loader.py`）

## 検討した選択肢

- **実在の名前のまま残す**：公開のリポジトリで、実在の製品の出力と誤解される。
  採らない
- **古い名前を新しい名前の別名として黙って読む**：利用者は、装置の擬態が
  効かなくなったことに気づけない。採らない

## 結果

- CT のテンプレートは `ct_generic`（`templates/modality/ct_generic.yaml`）に
  なり、中身の装置の名前は `DTG Synthetic`・`DTG Synthetic CT`・`DTG_CT` に
  なった。撮影の値（`ct_image`・`spatial`・`window_presets`）は変えていない
- 名前を替えたとき、装置の擬態の仕組みも一緒に消えた。仕組みは
  ADR-0012 の装置のプロファイルとして戻した

## 関連

- [ADR-0012](0012-device-profiles.md)
- [spec/13 装置のプロファイル](../spec/13_device_profiles.md) の 6.3・7.3
