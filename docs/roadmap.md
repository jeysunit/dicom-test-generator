# ロードマップ

- 作成日：2026-10-20
- 最終更新日：2026-10-22

まだ作っていないもの、まだ確かめていないものを並べる。作ったら spec に移し、
ここから消す。範囲に入れないと決めたものは
[project_charter.md](project_charter.md) の 4 章にある。

## 1. まだ確かめていないこと

- **Orthanc を相手にした保管確認。** 実装と試験（スタブを相手にしたもの）は
  済んでいる。Orthanc を相手に、送信キューの「保管確認」が「確認済」になることを
  手で確かめていない。手順はルートの [README](../README.md) の
  「Orthanc で保管確認を試す」にある

## 2. まだ作っていないもの

| 項目 | 今の状態 | 関係する文書 |
|------|----------|--------------|
| CT 以外のモダリティ（MR・CR・DX・US など） | 作れる SOP Class は CT Image Storage だけ | [spec/13](spec/13_device_profiles.md) の 4.3 |
| 装置のプロファイルの `uid`・`pixel`・`series` の欄 | モデルに欄が無く、書くと検証の誤りになる | [spec/13](spec/13_device_profiles.md) の 3.1・11 章 |
| 装置のプロファイルの `worklist` の欄 | 予約からの写し方はプロファイルで変えられない | [spec/13](spec/13_device_profiles.md) の 8 章 |
| 装置のプロファイルの `services.modality_worklist` | 値を持つだけで、動きに効かない | [spec/13](spec/13_device_profiles.md) の 3.1 |
| 表せない字を `?` に置き換えて撮る異常のデータ | 表せない字があれば必ず止まる | [ADR-0018](decisions/0018-stop-on-unrepresentable-characters.md) |
| 色と文字の値（デザイントークン）を1か所のファイルに持つ | 入力の CSS に値を書き、試験で表と比べている | [spec/12a](spec/12a_web_screens_and_cli.md) の 10.1 |

## 3. まだ決めていないこと

- **デスクトップの画面（PySide6）を外すか。** Web 画面が、今のデスクトップの
  画面でできる生成をすべて持てたら、別の PR で `app/gui/`・PySide6・pytest-qt を
  外す（[ADR-0011](decisions/0011-modality-emulator.md) の案 B）。Web 画面は
  予約と緊急の患者からの撮影を持つが、Job YAML や `quick` に当たる自由な生成は
  持たないので、まだ外さない。外す前に、Web 画面で同じことができることを
  確かめる試験を足す
- **ダークテーマで、主の色を文字（リンクなど）に使うときの色。** `#1f6feb` は
  ダークテーマの背景の上では文字に使えない（[spec/12a](spec/12a_web_screens_and_cli.md)
  の 10.2）。使うときに明るい色を別に決める
