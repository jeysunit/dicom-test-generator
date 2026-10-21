# ADR-0016: 公開のテンプレートと例の装置プロファイルに商用製品の名前を使わない

- 状態：採用
- 作成日：2026-10-22
- 最終更新日：2026-10-22

## 背景

CT のモダリティテンプレートは、名前と内容（`manufacturer`・
`manufacturers_model_name`・`station_name` など）に実在の製品の名前を使っていた。
このリポジトリは公開しているので、生成した画像が実在の製品の出力と誤解される
おそれがある。

## 決定

1. **テンプレートの名前は一般的な名前にし、商用製品の名前・会社の名前を使わない。**
   命名規則は `<モダリティ>_<部位や用途>_<番号や特徴>`（小文字・`_` 区切り）。
   例：`ct_generic`・`ct_chest_5mm`・`mr_head_generic`
2. 公開のテンプレートと、公開の例の装置プロファイル（`profiles/examples/`）の
   名前・`manufacturer`・`manufacturers_model_name`・`station_name` に商用の名前を
   書かない。`DTG Synthetic CT` のような架空の名前にする
3. 実在の装置に似せたいときは、装置プロファイルを使う
   （[ADR-0012](0012-device-profiles.md)）。リポジトリの外に置く装置プロファイルには、
   この規則を適用しない
4. 古い名前を指定した Job YAML・CLI には、装置プロファイルの配置場所を案内する
   エラーを返す。`TemplateNotFoundError` の `hint` に案内を入れ、別名として黙って
   読み込まない。古い名前は商用の名前を含むので、コードには名前そのものではなく
   SHA-256 のハッシュ値で持つ（`app/services/template_loader.py`）

## 検討した選択肢

- **実在の名前のまま残す**：公開のリポジトリで、実在の製品の出力と誤解される。
  採用しない
- **古い名前を新しい名前の別名として黙って読み込む**：装置の再現が無効になった
  ことに利用者が気付けない。採用しない

## 結果

- CT のテンプレートは `ct_generic`（`templates/modality/ct_generic.yaml`）になり、
  内容の装置の名前は `DTG Synthetic`・`DTG Synthetic CT`・`DTG_CT` になった。
  撮影の値（`ct_image`・`spatial`・`window_presets`）は変えていない
- 名前を変えたとき、装置を再現する仕組みも一緒に無くなった。仕組みは ADR-0012 の
  装置プロファイルとして戻した

## 関連

- [ADR-0012](0012-device-profiles.md)
- [spec/13 装置プロファイル](../spec/13_device_profiles.md) の 6.3・7.3
