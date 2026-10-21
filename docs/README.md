# 文書の索引

DTG（dicom-test-generator）の文書はこのディレクトリにあります。上から順に読むと
全体を把握できます。

| 文書 | 内容 | 更新するとき |
|------|------|--------------|
| [project_charter.md](project_charter.md) | 目的、範囲（機能の一覧）、規格に違反しないという前提と異常のデータの扱い | 目的や範囲が変わるとき |
| [usage.md](usage.md) | 使い方。インストールから撮影・送信・保管確認までの操作の順番 | 操作の手順が変わったとき |
| [architecture.md](architecture.md) | 全体の構成、層、ディレクトリ、生成の流れ | 構成が変わったとき |
| [spec/02_core_engine.md](spec/02_core_engine.md) | Core Engine の API：UID、ピクセル、File Meta、空間座標、Dataset の構築、異常のデータ | コードと同じ PR |
| [spec/03_data_models.md](spec/03_data_models.md) | データモデル（Pydantic） | コードと同じ PR |
| [spec/04_cli.md](spec/04_cli.md) | 生成の CLI（`generate`・`validate`・`quick` など）と終了コード | コードと同じ PR |
| [spec/05_gui.md](spec/05_gui.md) | PySide6 のデスクトップ画面（機能は追加しない） | コードと同じ PR |
| [spec/06_dicom_rules.md](spec/06_dicom_rules.md) | DICOM の規則：通常の経路と異常のデータの経路、File Meta、UID、Pixel Data、文字コード、Transfer Syntax | コードと同じ PR |
| [spec/07_job_schema.md](spec/07_job_schema.md) | Job YAML のスキーマ | コードと同じ PR |
| [spec/08_error_handling.md](spec/08_error_handling.md) | 例外の階層と終了コード | コードと同じ PR |
| [spec/09_logging.md](spec/09_logging.md) | ログ | コードと同じ PR |
| [spec/12_modality_emulator.md](spec/12_modality_emulator.md) | モダリティエミュレーター：通信、ワークリスト、予約の値の転記、文字コード、送信、保管確認、MPPS、層、設定、ログ、既知の制約、出典（1〜9 章と 12〜15 章） | コードと同じ PR |
| [spec/12a_web_screens_and_cli.md](spec/12a_web_screens_and_cli.md) | モダリティエミュレーターの Web 画面と CLI（10・11 章） | コードと同じ PR |
| [spec/13_device_profiles.md](spec/13_device_profiles.md) | 装置プロファイル | コードと同じ PR |
| [decisions/README.md](decisions/README.md) | 設計の判断とその理由（ADR）の一覧 | ADR を追加したとき |
| [roadmap.md](roadmap.md) | 未実装のもの、未確認のもの、未決定のもの | 実装したら spec に移し、ここから削除する |
| [development.md](development.md) | 開発環境、テスト、CI、確認のコマンド | 手順が変わったとき |

spec のファイル番号と、12・12a の章番号には欠番があります。コードのコメントが
番号で spec を参照しているため、番号を振り直していません。

## 書き方

文書とコードに共通の規則です。ADR に固有の規則は
[decisions/README.md](decisions/README.md) にあります。

### 文書の役割

同じ説明を2か所に書かず、次の役割で分けます。

- ルートの README：何をするものかと、最初に試す手順だけ
- [usage.md](usage.md)：利用者の操作の順番。オプションと設定の一覧は spec を参照する
- spec：現在の動作。コードと同じ PR で更新し、常に現在の動作に合わせる。規格に
  従う記述には、規格の節番号（例：PS3.4 K.6.1）を出典として書く
- ADR：設計の判断と理由。採用後は本文を書き換えない
- roadmap：未実装のもの

spec とコードが食い違っていたら、どちらが正しいかを確認し、誤っている側を
修正します。

### 文書の書き方

- 日本語は、日本のエンジニアが技術文書で普通に使う言葉で書きます。専門用語は
  そのまま使い、和語に言い換えません（例：「確認」を「確かめ」、「実行する」を
  「流す」、「取得する」を「引く」にしない）。計画の区切りは「フェーズ N」か
  「今後」と書きます
- 本文は 80 字で折り返し、`.markdownlint-cli2.yaml` の規則に従います。コード
  ブロックには言語（`python`・`bash`・`yaml`・`text` など）を書きます
- 図の矢印はデータが流れる向きにそろえ、ラベルには流れるもの（名詞）を書きます。
  要求の向き（誰が問い合わせるか）では描きません
- 作成日と最終更新日の行は ADR にだけ書きます（[decisions/README.md](decisions/README.md)）

### 変更の手順

作業は `main` から作成したブランチで行い、PR でマージします。`main` に直接
commit・push しません。1つの PR には1つの目的だけを入れます。動作を変えるときは、
次の順に更新します。

1. spec を更新する
2. 設計の判断（方式の選択、規格が許す形式のどれを選ぶか）を伴うなら、ADR を作成する
3. テストを先に書き、コードを変更する。バグを修正するときは、再発を防ぐテストを
   先に書く
4. 使い方が変わるなら、usage.md を更新する

spec に無い機能は追加しません。仕様の不明な点を推測で補って実装しません。既存の
テストに合格させるために仕様を変えません（実装を修正します）。

### コーディング規約

- 層の構造は [architecture.md](architecture.md) の 2 章のとおり。UI から Core
  Engine を直接呼ばない。Core Engine は UI・ログ・設定ファイルに依存しない
- Python 3.10 以上で動作させ、型ヒントを付ける。PEP 8 に従う（ruff は、設定
  ファイルが無く、現在のコードに指摘が残っているため、CI にはまだ入れていない）
- データモデルは Pydantic v2
- 命名は snake_case（関数・変数）、PascalCase（クラス）、UPPER_CASE（定数）。
  マジックナンバーは定数にする
- 1ファイル 800 行以下、1関数 50 行以下を目安にする。既存のオブジェクトを変更
  せず、新しく生成するほうを選ぶ
- 依存は `requirements.txt` で管理する。標準ライブラリで済むなら外部の
  パッケージを追加しない
- 例外は [spec/08](spec/08_error_handling.md) の階層に従う。基底の例外は
  `DICOMGeneratorError` で、汎用の `Exception` や `ValueError` を直接 raise
  しない。Core Engine は raise し、Service Layer は捕捉してログに出力し、UI Layer
  は捕捉して利用者に表示する。`except Exception:` で握りつぶさない。エラー
  メッセージには原因と文脈（入力の ID、処理の段階）を含める
- ログは [spec/09](spec/09_logging.md) に従う。`print()` ではなく `logging` を
  使う（CLI が利用者に表示する結果とエラーを除く）。Core Engine はログを出力
  しない。患者の氏名・生年月日などの個人情報と秘密情報をログに出力しない
- CLI は [spec/04](spec/04_cli.md) に従う。結果は標準出力、エラーは標準エラー
  出力に出す。`--help` で必須の引数と使用例を示す
- 新しい機能には、正常系と異常系のテストを追加する。カバレッジは 80% 以上を
  目標にする。Core Engine のテストでは、ファイルやネットワークを使わない

### Git

- ブランチ名は `<type>/<topic>`（`feature/`・`fix/`・`refactor/`・`docs/`・
  `test/`）
- commit メッセージは Conventional Commits の形式（`feat:`・`fix:`・
  `refactor:`・`test:`・`docs:`・`chore:`）。説明は日本語でよい。1つの commit
  には1つの論理的な変更だけを入れる
- 秘密情報（API キー・パスワードなど）は commit しない
- PR には、目的・変更点・確認方法・影響範囲を書く
