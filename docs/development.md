# 開発

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 1. 環境

Python 3.10 以上。試験の依存（pytest・pytest-qt・httpx）も `requirements.txt` に
入っている。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 2. 変更の進め方

作業は `main` から切ったブランチで行い、PR でマージする。`main` に直接 commit・
push しない。1つの PR には1つの目的だけを入れる。

振る舞いを変えるときは、次の順に直す。

1. spec を直す。spec は今どう動くかを書く文書なので、コードと同じ PR で直し、
   いつも今の振る舞いに合わせておく。規格に従う箇所には、規格の節番号を書く
   （[project_charter.md](project_charter.md) の 2 章）
2. 設計の判断（方式の選択、規格が許す形のどれを選ぶか）を伴うなら、ADR を起こす。
   書き方は [decisions/README.md](decisions/README.md) にある
3. 試験を先に書き、コードを直す。バグを直すときは、再発を防ぐ試験を先に書く
4. 使い方が変わるなら、ルートの README を直す

spec に無い機能は足さない。仕様の不明な点を推測で埋めて実装しない。既存の試験を
通すために仕様を変えない（実装を直す）。

## 3. コードの決まり

### 3.1 層

層の構造は [architecture.md](architecture.md) の 2 章のとおり。

- UI から Core Engine を直接呼ばない
- Core Engine は UI・ログ・設定ファイルに依存しない
- `app/modality/` は Service Layer の一部で、`app/services/`・`app/core/` だけを
  import する

### 3.2 Python

- Python 3.10 以上で動かす。型ヒントを付ける
- PEP 8 に従う。ruff は、設定のファイルが無く、今のコードに指摘が残っているため、
  CI にはまだ入れていない
- データモデルは Pydantic v2
- 名前は snake_case（関数・変数）、PascalCase（クラス）、UPPER_CASE（定数）。
  マジックナンバーは定数にする
- 1ファイル 800 行以下、1関数 50 行以下を目安にする。既存のオブジェクトを
  書き換えず、新しく作るほうを選ぶ
- 依存は `requirements.txt` で管理する。標準ライブラリで済むなら外部の
  パッケージを足さない

### 3.3 例外

[spec/08](spec/08_error_handling.md) の例外の階層に従う。

- ベースの例外は `DICOMGeneratorError`。汎用の `Exception` や `ValueError` を
  直接 raise しない
- Core Engine は例外を raise する（ログは出さない）。Service Layer は捕まえて
  ログに出し、必要なら raise し直す。UI Layer は捕まえて利用者に見せる
- `except Exception:` で握りつぶさない。エラーを隠して成功扱いにしない
- エラーメッセージには、原因と文脈（入力の ID、処理の段階）を入れる

### 3.4 ログ

[spec/09](spec/09_logging.md) に従う。

- `print()` ではなく `logging` を使う。例外は、CLI が利用者に見せる結果と
  エラーで、標準出力と標準エラーに出す
- Core Engine はログを出さない。Service Layer 以上で出す
- ロガーの名前は `logging.getLogger(__name__)`
- 患者の氏名・生年月日などの個人情報と秘密の値をログに出さない
- DEBUG のログは `logger.debug("msg: %s", obj)` の形で、文字列の組み立てを
  遅らせる

### 3.5 CLI

[spec/04](spec/04_cli.md) に従う。

- 入口は `python -m app.cli`
- 終了コードは 0=成功、1=一般のエラー、2=設定のエラー、3=I/O のエラー、
  4=バリデーションのエラー、5=通信のエラー
  （[spec/12a](spec/12a_web_screens_and_cli.md) の 11.6）
- 結果は標準出力、エラーは標準エラーに出す
- `--help` で必須の引数と使用例を示す

## 4. 試験

```bash
# 全部
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

# 表示の無い環境で GUI の試験を流す（CI と同じ）
QT_QPA_PLATFORM=offscreen pytest
```

新しい機能には、正常系と異常系の試験を足す。カバレッジは 80% 以上を目標にする。
Core Engine の試験では、ファイルやネットワークを使わない。

### 4.1 試験の構成

試験は層に合わせてディレクトリを分ける。

| ディレクトリ | 対象 |
|--------------|------|
| `tests/core/` | Core の各モジュール（単体）。予約から画像への写し方（[spec/12](spec/12_modality_emulator.md) の 6 章の表の行ごと）、4つの文字コードでの書き出しと読み戻し、装置のプロファイルのモデル |
| `tests/services/` | Service。テンプレート・患者・装置のプロファイルの読み込みと生成 |
| `tests/cli/` | CLI のサブコマンドの終了コードと `--json` の形 |
| `tests/modality/` | `app/modality/`。MWL の C-FIND、C-STORE・C-ECHO、保管確認、MPPS |
| `tests/web/` | Web 画面（FastAPI の TestClient） |
| `tests/gui/` | デスクトップの画面（Qt の offscreen） |
| `tests/integration/` | 層をまたぐ流れ（予約から送信まで） |
| `tests/scripts/` | `scripts/` のスクリプト |

### 4.2 通信の試験

本物の PACS・RIS にはつながない。試験の中で pynetdicom の SCP をローカル
（`127.0.0.1`・空いているポート）に立てて流す。この SCP は試験のスタブで、
DTG の機能ではない。スタブは `tests/modality_peers.py` にある。

- MWL の SCP のスタブは、予約を YAML（合成の患者だけ）から作り、`EVT_C_FIND` の
  ハンドラーで返す。文字コードを変えた応答も作れる
- ポートは試験ごとに空いているものを取る。固定のポートを使わない
- 保管確認の SCP と MPPS の SCP のスタブは、結果を返す経路（同じ・別の
  Association）、返す Status、返す値を試験ごとに変えられる
  （[ADR-0021](decisions/0021-test-only-commitment-and-mpps-peers.md)）

主な試験の中身は次のとおり。

| 対象 | ファイル | 中身 |
|------|----------|------|
| 予約の写し方 | `tests/core/test_worklist_mapping.py` | 予約あり・予約なしで写した値（生年月日・性別が空の予約、Patient's Size を m のまま写す、予約なしで Request Attributes Sequence・Referenced Study Sequence が無いことを含む） |
| 文字コード | `tests/core/test_worklist_charset.py` | 4つの選択それぞれで、漢字・かな・半角カナの氏名を書き出して読み戻す。表せない字で止まる |
| MWL | `tests/modality/test_worklist_scu.py` | 条件の組、Pending の打ち切り、時間切れ、文字コードの読み取り |
| 送信 | `tests/modality/test_store_scu.py` | C-STORE・C-ECHO の成功・Warning・Failure・つながらない |
| 保管確認 | `tests/modality/test_commitment_scu.py` | 結果が別の Association で返る形と、同じ Association で返る形。要求から結果までのキューの状態、一部失敗、時間切れ、遅れて来た結果、相手が止まっている、悪い値（知らない Transaction UID・UID の形でない・知らない Event Type・要求に無い組・別の AE からの結果） |
| MPPS | `tests/modality/test_mpps_scu.py` | N-CREATE・N-SET の値（予約あり・予約なし）。IN PROGRESS から COMPLETED、撮影が止まったときの DISCONTINUED、相手が止まっていたときに残して `mpps retry` で送る、相手が断る、応答なしの後の `0x0111`・`0x0110`、送り先の固定、2つの手順が同時に送り直しても重ねない、プロファイルの `services.mpps: false` |
| 統合 | `tests/integration/test_modality_flow.py` | MWL の SCP → `exam --from-worklist --send` → Storage の SCP のスタブが受ける。受けた画像の値が予約と合う |
| Web | `tests/web/` | ページが開く、HTMX の部分の応答、ループバック以外で待ち受けて認証が無ければ起動しない、`Origin` と CSRF のトークンの確かめ、相手から来る値（`<script>`・制御文字）のエスケープ、画面から「取得→選ぶ→撮る→送る」の一連の流れ、CSS の `@theme` の値が [spec/12a](spec/12a_web_screens_and_cli.md) の 10.2 の表と同じこと（`tests/web/test_theme_tokens.py`） |
| 装置のプロファイル | `tests/core/test_device_profile.py` ほか | [spec/13](spec/13_device_profiles.md) の 10 章 |

## 5. CI

`.github/workflows/ci.yml` が、PR と `main` への push で次を流す。

- pytest（Python 3.10・3.12）。GUI の試験は Qt の offscreen で動かし、X の
  サーバーを立てない
- markdownlint（設定は `.markdownlint-cli2.yaml`）
- 文書の最終更新日（PR のときだけ。6 章）
- 画面の CSS：`scripts/build_css.sh` で作り直し、commit した
  `app/web/static/app.css` と差が無いことを確かめる
- Docker のイメージ：`Dockerfile` からイメージを作り（push しない）、CLI が
  root 以外のユーザーで動くこと、Web 画面が `0.0.0.0` で起動して HTTP Basic
  認証を求めること、パスワードのファイルが無ければ起動しないことを確かめる

## 6. 文書

### 6.1 置き場と書き分け

| 文書 | 何を書くか |
|------|------------|
| ルートの `README.md` | 入口と使い方 |
| `docs/spec/` | 今どう動くか。コードと同じ PR で直す |
| `docs/decisions/` | なぜそう決めたか（ADR）。採用した後は本文を書き換えない |
| `docs/roadmap.md` | まだ作っていないもの |

### 6.2 日付の行

ルートの `README.md` と `docs/` の下の文書（ADR とその雛形を除く）は、題の直後に
次の2行を置く。文書を Git の外へ渡したときにも、いつの内容かが分かるように
するためである。

```markdown
- 作成日：YYYY-MM-DD
- 最終更新日：YYYY-MM-DD
```

文書を直したら、最終更新日をその日にする。付け忘れは次のスクリプトで見つかる。
CI は PR のときに流す。

```bash
python scripts/check_doc_dates.py origin/main..HEAD
```

ADR は冒頭に「状態」「日付」「作成日」の3行を置く
（[decisions/README.md](decisions/README.md)）。

### 6.3 markdownlint

```bash
npx markdownlint-cli2 "**/*.md" "#.venv" "#.pytest_cache"
```

決まりは `.markdownlint-cli2.yaml` にある（本文は 80 字で折り返す）。コードの
ブロックには言語を書く（`python`・`bash`・`yaml`・`text` など）。

## 7. Git

ブランチの名前は `<type>/<topic>` にする。

```text
feature/<機能名>
fix/<修正内容>
refactor/<対象>
docs/<対象>
test/<対象>
```

commit のメッセージは Conventional Commits の形（`feat:`・`fix:`・`refactor:`・
`test:`・`docs:`・`chore:`）。説明は日本語でよい。1つの commit には1つの
論理的な変更だけを入れる。秘密の値（API キー・パスワードなど）は commit しない。
PR には、目的・変更点・確かめ方・影響の範囲を書く。

## 8. Web 画面の静的ファイル

Web 画面の htmx・アイコン・CSS は、版を固定して `app/web/static/` に置き、
commit している。利用者がこれらを用意する必要は無い。

| ファイル | 版 | 入手元 | sha256 |
|----------|----|--------|--------|
| htmx（`app/web/static/htmx.min.js`） | v2.0.9 | GitHub の bigskysoftware/htmx の releases | `57d9191515339922bd1356d7b2d80b1ee3b29f1b3a2c65a078bb8b2e8fd9ae5f` |
| Lucide のアイコン（`app/web/static/icons/`。ISC License、同じ所に `LICENSE`） | 1.48.0 | GitHub の lucide-icons/lucide の releases（`lucide-icons-1.48.0.zip`） | `e27a6b58bebc563581f89668a5a652782075a85a07568e4fd8051a17ce81dba6`（zip） |
| Tailwind CSS の standalone の実行ファイル（CSS を作るときだけ） | v4.3.3 | GitHub の tailwindlabs/tailwindcss の releases | `scripts/build_css.sh` に OS ごとに固定 |

版を上げるときは、スクリプトの版と sha256 を直して流す。どちらも sha256 が
合わなければ止まる。

```bash
bash scripts/fetch_web_assets.sh   # htmx と Lucide のアイコン
bash scripts/build_css.sh          # app/web/styles/input.css から app/web/static/app.css を作る
```
