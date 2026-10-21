# 開発

開発環境、テスト、CI と、変更を確認するコマンドをまとめる。規則（変更の手順・
コーディング規約・Git・文書の書き方）は [README.md](README.md) の「書き方」にある。

## 1. 環境

Python 3.10 以上が必要。テストの依存（pytest・pytest-qt・httpx）も
`requirements.txt` に含まれている。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 2. 確認のコマンド

PR を作成する前に、次を実行する。

```bash
# テスト（ディスプレイの無い環境では QT_QPA_PLATFORM=offscreen を付ける）
QT_QPA_PLATFORM=offscreen pytest

# Markdown
npx markdownlint-cli2 "**/*.md" "#.venv" "#.pytest_cache"

# ADR の最終更新日の記入漏れ
python scripts/check_doc_dates.py origin/main..HEAD
```

## 3. CI

`.github/workflows/ci.yml` が、PR と `main` への push で次を実行する。

- pytest（Python 3.10・3.12）。GUI のテストは Qt の offscreen で実行し、X の
  サーバーを起動しない
- markdownlint（設定は `.markdownlint-cli2.yaml`）
- ADR の最終更新日の検証（PR のときだけ）
- 画面の CSS：`scripts/build_css.sh` で生成し直し、commit した
  `app/web/static/app.css` と差分が無いことを確認する
- Docker イメージ：`Dockerfile` からイメージをビルドし（push しない）、CLI が
  root 以外のユーザーで動くこと、Web 画面が `0.0.0.0` で起動して HTTP Basic 認証を
  求めること、パスワードのファイルが無ければ起動しないことを確認する

## 4. テスト

```bash
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
```

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

## 5. Web 画面の静的ファイル

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
