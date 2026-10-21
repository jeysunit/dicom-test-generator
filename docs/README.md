# 文書の索引

- 作成日：2026-10-22
- 最終更新日：2026-10-22

DTG（dicom-test-generator）の文書はこのディレクトリにあります。使い方はルートの
[README](../README.md) を読んでください。ここには、作りを知りたい人と、直したい人の
ための文書を置いています。

## 文書の種類

| 種類 | 何を書くか | 直し方 |
|------|------------|--------|
| [project_charter.md](project_charter.md) | 目的、範囲、規格に違反しないという前提と、異常のデータの扱い | 目的や範囲が変わるときだけ直す |
| [architecture.md](architecture.md) | 全体の構成、層、ディレクトリ、生成の流れ | 構成が変わったら直す |
| [spec/](spec/) | 今どう動くか。規格の節番号を出典として書く | コードと同じ PR で直し、いつも今の振る舞いに合わせる |
| [decisions/](decisions/README.md) | なぜそう決めたか（ADR） | 採用した後は本文を書き換えない。判断を変えるときは新しい ADR を起こす |
| [roadmap.md](roadmap.md) | まだ作っていないもの、まだ確かめていないもの | 作ったら spec に移して消す |
| [development.md](development.md) | 開発の環境、変更の進め方、コードの決まり、試験、CI、文書の決まり | 手順が変わったら直す |

## 読む順

初めて触るときは、次の順に読むと全体がつかめます。

1. [project_charter.md](project_charter.md)
2. [architecture.md](architecture.md)
3. [spec/02_core_engine.md](spec/02_core_engine.md) と
   [spec/07_job_schema.md](spec/07_job_schema.md)：画像の作り方と Job の書き方
4. [spec/12_modality_emulator.md](spec/12_modality_emulator.md)：モダリティ
   エミュレーター
5. [development.md](development.md)

## spec

| ファイル | 中身 |
|----------|------|
| [02_core_engine.md](spec/02_core_engine.md) | Core Engine の API：UID、ピクセル、File Meta、空間座標、Dataset の構築、異常のデータ |
| [03_data_models.md](spec/03_data_models.md) | データモデル（Pydantic） |
| [04_cli.md](spec/04_cli.md) | 生成の CLI（`generate`・`validate`・`quick` など）と終了コード |
| [05_gui.md](spec/05_gui.md) | PySide6 のデスクトップの画面（機能は足さない） |
| [06_dicom_rules.md](spec/06_dicom_rules.md) | DICOM の規則：ふつうの経路と異常のデータの経路、File Meta、UID、Pixel Data、文字コード、Transfer Syntax |
| [07_job_schema.md](spec/07_job_schema.md) | Job YAML のスキーマ |
| [08_error_handling.md](spec/08_error_handling.md) | 例外の階層と終了コード |
| [09_logging.md](spec/09_logging.md) | ログ |
| [12_modality_emulator.md](spec/12_modality_emulator.md) | モダリティエミュレーター：通信、ワークリスト、予約の写し方、文字コード、送信、保管確認、MPPS、層、設定、ログ、既知の制約、出典（1〜9 章と 12〜15 章） |
| [12a_web_screens_and_cli.md](spec/12a_web_screens_and_cli.md) | モダリティエミュレーターの Web 画面と CLI（10・11 章） |
| [13_device_profiles.md](spec/13_device_profiles.md) | 装置のプロファイル |

spec のファイルの番号と、12・12a の章の番号には欠けがあります。コードの
コメントが番号で spec を指しているため、振り直していません。

## decisions

ADR の一覧と書き方は [decisions/README.md](decisions/README.md) にあります。

## 食い違いを見つけたとき

spec とコードが食い違っていたら、どちらが正しいかを確かめて、間違っている側を
直してください。ルートの README と docs が食い違っていたら、docs が正です。
