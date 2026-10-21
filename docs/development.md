# 開発

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 1. 環境

Python 3.10 以上が必要。テストの依存（pytest・pytest-qt・httpx）も
`requirements.txt` に含まれている。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 2. 変更の手順

作業は `main` から作成したブランチで行い、PR でマージする。`main` に直接 commit・
push しない。1つの PR には1つの目的だけを入れる。

動作を変えるときは、次の順に更新する。

1. spec を更新する。spec は現在の動作を書く文書なので、コードと同じ PR で更新し、
   常に現在の動作に合わせておく。規格に従う箇所には、規格の節番号を書く
   （[project_charter.md](project_charter.md) の 2 章）
2. 設計の判断（方式の選択、規格が許す形式のどれを選ぶか）を伴うなら、ADR を作成
   する。書き方は [decisions/README.md](decisions/README.md) にある
3. テストを先に書き、コードを変更する。バグを修正するときは、再発を防ぐテストを
   先に書く
4. 使い方が変わるなら、ルートの README を更新する

spec に無い機能は追加しない。仕様の不明な点を推測で補って実装しない。既存の
テストに合格させるために仕様を変えない（実装を修正する）。

## 3. コーディング規約

### 3.1 層

層の構造は [architecture.md](architecture.md) の 2 章のとおり。

- UI から Core Engine を直接呼ばない
- Core Engine は UI・ログ・設定ファイルに依存しない
- `app/modality/` は Service Layer の一部で、`app/services/`・`app/core/` だけを
  import する

### 3.2 Python

- Python 3.10 以上で動作させる。型ヒントを付ける
- PEP 8 に従う。ruff は、設定ファイルが無く、現在のコードに指摘が残っているため、
  CI にはまだ入れていない
- データモデルは Pydantic v2
- 命名は snake_case（関数・変数）、PascalCase（クラス）、UPPER_CASE（定数）。
  マジックナンバーは定数にする
- 1ファイル 800 行以下、1関数 50 行以下を目安にする。既存のオブジェクトを
  変更せず、新しく生成するほうを選ぶ
- 依存は `requirements.txt` で管理する。標準ライブラリで済むなら外部の
  パッケージを追加しない

### 3.3 例外

[spec/08](spec/08_error_handling.md) の例外の階層に従う。

- 基底の例外は `DICOMGeneratorError`。汎用の `Exception` や `ValueError` を
  直接 raise しない
- Core Engine は例外を raise する（ログは出力しない）。Service Layer は捕捉して
  ログに出力し、必要なら再送出する。UI Layer は捕捉して利用者に表示する
- `except Exception:` で例外を握りつぶさない。エラーを隠して成功として扱わない
- エラーメッセージには、原因と文脈（入力の ID、処理の段階）を含める

### 3.4 ログ

[spec/09](spec/09_logging.md) に従う。

- `print()` ではなく `logging` を使う。例外は CLI が利用者に表示する結果と
  エラーで、標準出力と標準エラー出力に出す
- Core Engine はログを出力しない。Service Layer 以上で出力する
- ロガーの名前は `logging.getLogger(__name__)`
- 患者の氏名・生年月日などの個人情報と秘密情報をログに出力しない
- DEBUG のログは `logger.debug("msg: %s", obj)` の形で書き、文字列の組み立てを
  遅延させる

### 3.5 CLI

[spec/04](spec/04_cli.md) に従う。

- エントリポイントは `python -m app.cli`
- 終了コードは 0=成功、1=一般エラー、2=設定エラー、3=I/O エラー、
  4=バリデーションエラー、5=通信エラー
  （[spec/12a](spec/12a_web_screens_and_cli.md) の 11.6）
- 結果は標準出力、エラーは標準エラー出力に出す
- `--help` で必須の引数と使用例を示す

## 4. テスト

```bash
# すべて
pytest

# 層ごと
pytest tests/core/ -v
pytest tests/services/ -v
pytest tests/cli/ -v
pytest tests/modality/ -v
pytest tests/integration/ -v
pytest tests/gui/ -v
pytest tests/web/ -v

# カバレッジ
pytest --cov=app --cov-report=term-missing

# ディスプレイの無い環境で GUI のテストを実行する（CI と同じ）
QT_QPA_PLATFORM=offscreen pytest
```

新しい機能には、正常系と異常系のテストを追加する。カバレッジは 80% 以上を目標に
する。Core Engine のテストでは、ファイルやネットワークを使わない。

### 4.1 テストの構成

テストは層に合わせてディレクトリを分ける。

| ディレクトリ | 対象 |
|--------------|------|
| `tests/core/` | Core の各モジュール（単体）。予約の値の転記（[spec/12](spec/12_modality_emulator.md) の 6 章の表の行ごと）、4つの文字コードでのエンコードとデコード、装置プロファイルのモデル |
| `tests/services/` | Service。テンプレート・患者・装置プロファイルの読み込みと生成 |
| `tests/cli/` | CLI のサブコマンドの終了コードと `--json` の形式 |
| `tests/modality/` | `app/modality/`。MWL の C-FIND、C-STORE・C-ECHO、保管確認、MPPS |
| `tests/web/` | Web 画面（FastAPI の TestClient） |
| `tests/gui/` | デスクトップ画面（Qt の offscreen） |
| `tests/integration/` | 層をまたぐ流れ（予約から送信まで） |
| `tests/scripts/` | `scripts/` のスクリプト |

### 4.2 通信のテスト

本番の PACS・RIS には接続しない。テストの中で pynetdicom の SCP をローカル
（`127.0.0.1`・空いているポート）に起動して実行する。この SCP はテスト用のスタブで、
DTG の機能ではない。スタブは `tests/modality_peers.py` にある。

- MWL の SCP のスタブは、予約を YAML（合成した患者だけ）から生成し、`EVT_C_FIND`
  のハンドラーで返す。文字コードを変えた応答も生成できる
- ポートはテストごとに空いているものを使う。固定のポートは使わない
- 保管確認の SCP と MPPS の SCP のスタブは、結果を返す経路（同じ・別の
  Association）、返す Status、返す値をテストごとに変えられる
  （[ADR-0021](decisions/0021-test-only-commitment-and-mpps-peers.md)）

主なテストの内容は次のとおり。

| 対象 | ファイル | 内容 |
|------|----------|------|
| 予約の値の転記 | `tests/core/test_worklist_mapping.py` | 予約あり・予約なしで転記した値（生年月日・性別が空の予約、Patient's Size を m のまま転記する、予約なしで Request Attributes Sequence・Referenced Study Sequence が無いことを含む） |
| 文字コード | `tests/core/test_worklist_charset.py` | 4つの選択肢それぞれで、漢字・かな・半角カナの氏名をエンコードしてデコードする。表現できない文字で停止する |
| MWL | `tests/modality/test_worklist_scu.py` | 検索条件の組み合わせ、Pending の打ち切り、タイムアウト、文字コードの読み取り |
| 送信 | `tests/modality/test_store_scu.py` | C-STORE・C-ECHO の成功・Warning・Failure・接続失敗 |
| 保管確認 | `tests/modality/test_commitment_scu.py` | 結果が別の Association で返る形と、同じ Association で返る形。要求から結果までのキューの状態、一部失敗、タイムアウト、遅れて届いた結果、相手が停止している、不正な値（未知の Transaction UID・UID の形式でない・未知の Event Type・要求に無い組・別の AE からの結果） |
| MPPS | `tests/modality/test_mpps_scu.py` | N-CREATE・N-SET の値（予約あり・予約なし）。IN PROGRESS から COMPLETED、撮影が止まったときの DISCONTINUED、相手が停止していたときにキューに残して `mpps retry` で送信する、相手が拒否する、応答なしの後の `0x0111`・`0x0110`、送信先の固定、2つの処理が同時に再送しても重複しない、プロファイルの `services.mpps: false` |
| 統合 | `tests/integration/test_modality_flow.py` | MWL の SCP → `exam --from-worklist --send` → Storage の SCP のスタブが受信する。受信した画像の値が予約と一致する |
| Web | `tests/web/` | ページが表示される、HTMX の部分応答、ループバック以外で待ち受けて認証が無ければ起動しない、`Origin` と CSRF トークンの検証、相手から来る値（`<script>`・制御文字）のエスケープ、画面から「取得→選択→撮影→送信」の一連の流れ、CSS の `@theme` の値が [spec/12a](spec/12a_web_screens_and_cli.md) の 10.2 の表と一致すること（`tests/web/test_theme_tokens.py`） |
| 装置プロファイル | `tests/core/test_device_profile.py` ほか | [spec/13](spec/13_device_profiles.md) の 10 章 |

## 5. CI

`.github/workflows/ci.yml` が、PR と `main` への push で次を実行する。

- pytest（Python 3.10・3.12）。GUI のテストは Qt の offscreen で実行し、X の
  サーバーを起動しない
- markdownlint（設定は `.markdownlint-cli2.yaml`）
- 文書の最終更新日の検証（PR のときだけ。6 章）
- 画面の CSS：`scripts/build_css.sh` で生成し直し、commit した
  `app/web/static/app.css` と差分が無いことを確認する
- Docker イメージ：`Dockerfile` からイメージをビルドし（push しない）、CLI が
  root 以外のユーザーで動くこと、Web 画面が `0.0.0.0` で起動して HTTP Basic 認証を
  求めること、パスワードのファイルが無ければ起動しないことを確認する

## 6. 文書

文書の書き方（役割の分け方、作成日と最終更新日の行、言葉の選び方）は
[docs/README.md](README.md) の「書き方」にある。ここには検証の方法だけを書く。

```bash
# 最終更新日の記入漏れを検出する
python scripts/check_doc_dates.py origin/main..HEAD

# markdownlint
npx markdownlint-cli2 "**/*.md" "#.venv" "#.pytest_cache"
```

## 7. Git

ブランチ名は `<type>/<topic>` にする。

```text
feature/<機能名>
fix/<修正内容>
refactor/<対象>
docs/<対象>
test/<対象>
```

commit メッセージは Conventional Commits の形式（`feat:`・`fix:`・`refactor:`・
`test:`・`docs:`・`chore:`）にする。説明は日本語でよい。1つの commit には1つの
論理的な変更だけを入れる。秘密情報（API キー・パスワードなど）は commit しない。
PR には、目的・変更点・確認方法・影響範囲を書く。

## 8. Web 画面の静的ファイル

Web 画面の htmx・アイコン・CSS は、バージョンを固定して `app/web/static/` に置き、
commit している。利用者がこれらを用意する必要は無い。

| ファイル | バージョン | 入手元 | sha256 |
|----------|------------|--------|--------|
| htmx（`app/web/static/htmx.min.js`） | v2.0.9 | GitHub の bigskysoftware/htmx の releases | `57d9191515339922bd1356d7b2d80b1ee3b29f1b3a2c65a078bb8b2e8fd9ae5f` |
| Lucide のアイコン（`app/web/static/icons/`。ISC License、同じ場所に `LICENSE`） | 1.48.0 | GitHub の lucide-icons/lucide の releases（`lucide-icons-1.48.0.zip`） | `e27a6b58bebc563581f89668a5a652782075a85a07568e4fd8051a17ce81dba6`（zip） |
| Tailwind CSS の standalone の実行ファイル（CSS を生成するときだけ） | v4.3.3 | GitHub の tailwindlabs/tailwindcss の releases | `scripts/build_css.sh` に OS ごとに固定 |

バージョンを上げるときは、スクリプトのバージョンと sha256 を変更して実行する。
どちらのスクリプトも、sha256 が一致しなければ停止する。

```bash
bash scripts/fetch_web_assets.sh   # htmx と Lucide のアイコン
bash scripts/build_css.sh          # app/web/styles/input.css から app/web/static/app.css を生成する
```
