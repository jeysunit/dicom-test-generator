# 文書の索引

- 作成日：2026-10-22
- 最終更新日：2026-10-22

DTG（dicom-test-generator）の文書はこのディレクトリにあります。使い方はルートの
[README](../README.md) を読んでください。ここには、構成を知りたい人と、コードを
変更したい人のための文書を置いています。

## 索引

| 文書 | 内容 | 更新するとき |
|------|------|--------------|
| [project_charter.md](project_charter.md) | 目的、範囲、規格に違反しないという前提と、異常のデータの扱い | 目的や範囲が変わるとき |
| [architecture.md](architecture.md) | 全体の構成、層、ディレクトリ、生成の流れ | 構成が変わったとき |
| [spec/](spec/) | 現在の動作。規格の節番号を出典として書く | コードと同じ PR で更新し、常に現在の動作に合わせる |
| [decisions/](decisions/README.md) | 設計の判断とその理由（ADR） | 採用後は本文を書き換えない。判断を変えるときは新しい ADR を作成する |
| [roadmap.md](roadmap.md) | 未実装のもの、未確認のもの | 実装したら spec に移し、ここから削除する |
| [development.md](development.md) | 開発環境、変更の手順、コーディング規約、テスト、CI | 手順が変わったとき |

### 読む順番

初めて読むときは、次の順番で読むと全体を把握できます。

1. [project_charter.md](project_charter.md)
2. [architecture.md](architecture.md)
3. [spec/02_core_engine.md](spec/02_core_engine.md) と
   [spec/07_job_schema.md](spec/07_job_schema.md)：画像の生成と Job の書き方
4. [spec/12_modality_emulator.md](spec/12_modality_emulator.md)：モダリティ
   エミュレーター
5. [development.md](development.md)

### spec の一覧

| ファイル | 内容 |
|----------|------|
| [02_core_engine.md](spec/02_core_engine.md) | Core Engine の API：UID、ピクセル、File Meta、空間座標、Dataset の構築、異常のデータ |
| [03_data_models.md](spec/03_data_models.md) | データモデル（Pydantic） |
| [04_cli.md](spec/04_cli.md) | 生成の CLI（`generate`・`validate`・`quick` など）と終了コード |
| [05_gui.md](spec/05_gui.md) | PySide6 のデスクトップ画面（機能は追加しない） |
| [06_dicom_rules.md](spec/06_dicom_rules.md) | DICOM の規則：通常の経路と異常のデータの経路、File Meta、UID、Pixel Data、文字コード、Transfer Syntax |
| [07_job_schema.md](spec/07_job_schema.md) | Job YAML のスキーマ |
| [08_error_handling.md](spec/08_error_handling.md) | 例外の階層と終了コード |
| [09_logging.md](spec/09_logging.md) | ログ |
| [12_modality_emulator.md](spec/12_modality_emulator.md) | モダリティエミュレーター：通信、ワークリスト、予約の値の転記、文字コード、送信、保管確認、MPPS、層、設定、ログ、既知の制約、出典（1〜9 章と 12〜15 章） |
| [12a_web_screens_and_cli.md](spec/12a_web_screens_and_cli.md) | モダリティエミュレーターの Web 画面と CLI（10・11 章） |
| [13_device_profiles.md](spec/13_device_profiles.md) | 装置プロファイル |

spec のファイル番号と、12・12a の章番号には欠番があります。コードのコメントが
番号で spec を参照しているため、番号を振り直していません。

ADR の一覧は [decisions/README.md](decisions/README.md) にあります。

## 書き方

docs/ の下の文書とルートの README に共通の規則です。ADR に固有の規則は
[decisions/README.md](decisions/README.md) にあります。

- 文書の役割を分けます。ルートの README は概要と使い方、spec は現在の動作、
  ADR は判断と理由、roadmap は未実装のものを書きます
- 題の直後に、作成日と最終更新日の2行を置きます。文書を Git の外へ渡したときにも、
  いつの内容かが分かるようにするためです。ADR とその雛形は対象外です

  ```markdown
  - 作成日：YYYY-MM-DD
  - 最終更新日：YYYY-MM-DD
  ```

- 文書を変更したら、最終更新日をその日にします。記入漏れは
  `python scripts/check_doc_dates.py origin/main..HEAD` で検出でき、CI も PR の
  ときに実行します
- 規格に従う記述には、規格の節番号（例：PS3.4 K.6.1）を出典として書きます
- 日本語は、日本のエンジニアが技術文書で普通に使う言葉で書きます。専門用語は
  そのまま使い、和語に言い換えません（例：「確認」を「確かめ」、「実行する」を
  「流す」、「取得する」を「引く」にしない）。計画の区切りは「フェーズ N」か
  「今後」と書きます
- 本文は 80 字で折り返し、`.markdownlint-cli2.yaml` の規則に従います。コード
  ブロックには言語（`python`・`bash`・`yaml`・`text` など）を書きます
- spec とコードが食い違っていたら、どちらが正しいかを確認し、誤っている側を
  直します。ルートの README と docs/ が食い違っていたら、docs/ が正です
