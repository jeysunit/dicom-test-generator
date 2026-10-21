# ロードマップ

- 作成日：2026-10-20
- 最終更新日：2026-10-22

未実装のものと、未確認のものを並べる。実装したら spec に移し、ここから削除する。
範囲に入れないと決めたものは [project_charter.md](project_charter.md) の 4 章に
ある。

## 1. 未確認のもの

- **Orthanc を相手にした保管確認。** 実装とテスト（スタブを相手にしたもの）は
  済んでいる。Orthanc を相手に、送信キューの「保管の確認」が「確認済」になることを
  手動で確認していない。手順はルートの [README](../README.md) の
  「Orthanc で保管確認をテストする」にある

## 2. 未実装のもの

| 項目 | 現在の状態 | 関係する文書 |
|------|------------|--------------|
| CT 以外のモダリティ（MR・CR・DX・US など） | 生成できる SOP Class は CT Image Storage だけ | [spec/13](spec/13_device_profiles.md) の 4.3 |
| 装置プロファイルの `uid`・`pixel`・`series` フィールド | モデルにフィールドが無く、書くと検証エラーになる | [spec/13](spec/13_device_profiles.md) の 3.1・11 章 |
| 装置プロファイルの `worklist` フィールド | 予約の値の転記方法はプロファイルで変えられない | [spec/13](spec/13_device_profiles.md) の 8 章 |
| 装置プロファイルの `services.modality_worklist` | 値を持つだけで、動作に反映されない | [spec/13](spec/13_device_profiles.md) の 3.1 |
| 表現できない文字を `?` に置き換えて撮影する異常のデータ | 表現できない文字があれば必ず停止する | [ADR-0018](decisions/0018-stop-on-unrepresentable-characters.md) |
| 色と文字の値（デザイントークン）を1か所のファイルで管理する | 入力の CSS に値を書き、テストで表と比較している | [spec/12a](spec/12a_web_screens_and_cli.md) の 10.1 |

## 3. 未決定のもの

- **デスクトップ画面（PySide6）を削除するか。** Web 画面が、現在のデスクトップ
  画面でできる生成をすべて持てたら、別の PR で `app/gui/`・PySide6・pytest-qt を
  削除する（[ADR-0011](decisions/0011-modality-emulator.md) の案 B）。Web 画面は
  予約と緊急の患者からの撮影を持つが、Job YAML や `quick` に相当する自由な生成は
  持たないので、まだ削除しない。削除する前に、Web 画面で同じことができることを
  確認するテストを追加する
- **ダークテーマで、主の色を文字（リンクなど）に使うときの色。** `#1f6feb` は
  ダークテーマの背景の上では文字に使えない（[spec/12a](spec/12a_web_screens_and_cli.md)
  の 10.2）。使うときに明るい色を別に決める
