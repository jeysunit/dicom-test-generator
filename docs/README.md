# ドキュメントの索引

DTG（dicom-test-generator）の使い方・設計・仕様・開発の手順を書いたドキュメントの
索引と、ドキュメントの書き方です。

## 索引

| ドキュメント | 内容 |
|--------------|------|
| [usage.md](usage.md) | 使い方：起動、Web 画面での撮影、送信の状態と再送信、保管確認（Storage Commitment）と MPPS、設定、CLI |
| [project_charter.md](project_charter.md) | 目的、範囲（機能の一覧）、規格に違反しないという前提と異常のデータの扱い |
| [architecture.md](architecture.md) | 全体の構成、モジュールの依存関係、DICOM 画像の作成の流れ、エラーの扱い、依存するパッケージ、セキュリティ |
| spec/（下の表） | 現在の動作 |
| [decisions/README.md](decisions/README.md) | ADR の一覧と、ADR に固有の書き方 |
| [roadmap.md](roadmap.md) | 未確認・未実装・未決定のもの |
| [development.md](development.md) | 開発環境、テスト、確認のコマンド、変更の手順、コーディング規約 |

### spec

| ファイル | 内容 |
|----------|------|
| [01_unused.md](spec/01_unused.md) | 欠番 |
| [02_core_engine.md](spec/02_core_engine.md) | Core レイヤー：UID、ピクセル、File Meta、空間座標、Dataset の構築、異常のデータ |
| [03_data_models.md](spec/03_data_models.md) | データモデル（Pydantic） |
| [04_cli.md](spec/04_cli.md) | DICOM 画像を作成する CLI（`generate`・`validate`・`quick` など）と終了コード |
| [05_gui.md](spec/05_gui.md) | 欠番 |
| [06_dicom_rules.md](spec/06_dicom_rules.md) | DICOM の規則：通常の経路と異常のデータの経路、File Meta、UID、Pixel Data、文字コード、Transfer Syntax |
| [07_job_schema.md](spec/07_job_schema.md) | Job YAML のスキーマ |
| [08_error_handling.md](spec/08_error_handling.md) | 例外の階層と終了コード |
| [09_logging.md](spec/09_logging.md) | ログ |
| [10_unused.md](spec/10_unused.md) | 欠番 |
| [11_unused.md](spec/11_unused.md) | 欠番 |
| [12_modality_emulator.md](spec/12_modality_emulator.md) | モダリティエミュレーター：通信、ワークリスト、予約の値の転記、文字コード、送信、保管確認、MPPS、モジュールと配置、設定、ログ、既知の制約、出典 |
| [12a_web_screens_and_cli.md](spec/12a_web_screens_and_cli.md) | モダリティエミュレーターの Web 画面と CLI |
| [13_device_profiles.md](spec/13_device_profiles.md) | 装置プロファイル |

## 書き方

- spec には現在の動作を書きます。コードと同じ PR で更新し、常に現在の動作に合わせます
- 規格に従って実装した箇所は、spec に規格の節番号を書きます（例 PS3.4 K.6.1、PS3.5 9.1）
- 規格が複数の形式を許すときは、どれを選んだかを spec に書き、選んだ理由を ADR に書きます
- 設計判断の理由は ADR に書きます。ADR の書き方は [decisions/README.md](decisions/README.md) に従います
- 使い方の手順は usage.md に書きます。オプションと設定の項目の一覧は spec に書き、
  usage.md からは参照します
- roadmap.md には未確認・未実装・未決定のものだけを書きます。実装したら spec に移し、
  roadmap.md から削除します
- project_charter.md は目的や範囲が変わるときだけ、architecture.md は構成が変わったとき、
  development.md は手順が変わったときに更新します
- 作成日と最終更新日の行は ADR にだけ書きます
- spec のファイル番号はコードのコメントが参照しているので、振り直しません。使わない
  番号は欠番のファイルにします
- Markdown の本文は 80 文字で折り返します（`.markdownlint-cli2.yaml` の MD013）。
  コードブロックには言語を書きます
- 図の矢印はデータが流れる向きに描き、ラベルには流れるもの（名詞）を書きます。
  要求を送る向きでは描きません
- 言葉は、読み手が普段使う言葉で書きます。エンジニアが普通に使う専門用語は、
  和語に言い換えずにそのまま使います。計画の区切りは「フェーズ N」か「今後」と書きます
- spec とコードが食い違っていたら、どちらが正しいかを確認し、誤っている側を修正します
- ルートの README と docs が食い違っていたら、docs を正とします
