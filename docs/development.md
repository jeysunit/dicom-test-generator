# 開発

開発環境、確認のコマンド、CI、テスト、変更の手順、コーディング規約をまとめる。
ドキュメントの書き方は [README.md の「書き方」](README.md#書き方) にある。

## 1. 環境

Python 3.10 以上が必要。テストの依存（pytest・httpx）も
`requirements.txt` に含まれている。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

設定のタイムゾーン（`modality.timezone`、IANA の名前）は、標準ライブラリの `zoneinfo`
で解く。Docker のイメージは OS のタイムゾーンのデータを持つが、Windows など Docker
以外の環境は OS にタイムゾーンのデータがないことがあり、その場合は `tzdata`
（`pip install tzdata`）が要る。`requirements.txt` には入れていない。入れていない環境で
`Asia/Tokyo` などを解けないと、設定の読み込みが断る。

Python の環境で Web 画面と CLI を動かすときは、リポジトリのディレクトリで実行する。
設定ファイルは `config/app_config.yaml` で、Web 画面は既定ではループバック
（127.0.0.1）だけで待ち受け、認証は無い。ループバック以外で待ち受けるときは、
コンテナと同じくパスワードのファイルを `DTG_WEB_PASSWORD_FILE` で指定する。

```bash
python -m app.web
python -m app.cli quick -p P000001 -m ct_generic -s 1 -i 3 -o output/
```

## 2. 確認のコマンド

PR を作成する前に、次を実行する。

```bash
# テスト
pytest

# Markdown の形式（設定は .markdownlint-cli2.yaml）
npx markdownlint-cli2 "**/*.md" "#.venv" "#.pytest_cache"

# ADR の最終更新日の記入漏れ
python scripts/check_doc_dates.py origin/main..HEAD
```

`check_doc_dates.py` は、指定した範囲で最後に変更したコミットの日付より ADR の
「最終更新日」が古いか、行が無ければ終了コード 1 で失敗する。

## 3. CI

`.github/workflows/ci.yml` が、PR と `main` への push で次を実行する。

- pytest（Python 3.10・3.12）
- markdownlint（設定は `.markdownlint-cli2.yaml`）
- ADR の最終更新日の検証（PR のときだけ）
- 画面の CSS：`scripts/build_css.sh` で作成し直し、commit した
  `app/web/static/app.css` と差分が無いことを確認する
- Docker イメージ：`Dockerfile` からイメージをビルドし（push しない）、CLI が
  root 以外のユーザーで動くこと、`--user` でホストの利用者として出力フォルダに
  書き出せること、イメージの中の設定のまま Web 画面が `0.0.0.0` で起動して HTTP Basic
  認証を求めること、パスワードのファイルが無ければ起動しないことを確認する

`.github/workflows/publish.yml` は、`v` で始まるタグの push と、手動の実行のときだけ
動き、イメージを `ghcr.io/jeysunit/dicom-test-generator` に公開する（タグは版と
`latest`。[ADR-0026](decisions/0026-container-image-distribution.md)）。手動で実行する
ときは、実行する ref に `v1.2.0` の形のタグを選ぶ（ほかの ref と、この形でないタグ
では失敗する）。`main` への
push と PR では動かない。

## 4. テスト

```bash
# ディレクトリごと
pytest tests/core/ -v
pytest tests/services/ -v
pytest tests/cli/ -v
pytest tests/modality/ -v
pytest tests/integration/ -v
pytest tests/web/ -v

# カバレッジ
pytest --cov=app --cov-report=term-missing
```

### 4.1 テストの構成

テストは `app/` のディレクトリに合わせて分ける。

| ディレクトリ | 対象 |
|--------------|------|
| `tests/core/` | `app/core/` の各モジュール（単体）。予約の値の転記（[spec/12](spec/12_modality_emulator.md) の 6 章の表の行ごと）、4つの文字コードでのエンコードとデコード、装置プロファイルのモデル |
| `tests/services/` | `app/services/`。テンプレート・患者・装置プロファイルの読み込みと、DICOM 画像の作成 |
| `tests/cli/` | CLI のサブコマンドの終了コードと `--json` の形式 |
| `tests/modality/` | `app/modality/`。MWL の C-FIND、C-STORE・C-ECHO、保管確認（Storage Commitment）、MPPS |
| `tests/web/` | Web 画面（FastAPI の TestClient） |
| `tests/integration/` | モジュールをまたぐ流れ（予約から送信まで） |
| `tests/scripts/` | `scripts/` のスクリプト |

### 4.2 通信のテスト

本番の PACS・RIS には接続しない。テストの中で pynetdicom の SCP をローカル
（`127.0.0.1`・空いているポート）に起動して実行する。この SCP はテスト用のスタブで、
DTG の機能ではない。スタブは `tests/modality_peers.py` にある。

- MWL の SCP のスタブは、予約を YAML（合成した患者だけ）から作成し、`EVT_C_FIND`
  のハンドラーで返す。文字コードを変えた応答も作成できる
- ポートはテストごとに空いているものを使う。固定のポートは使わない
- 試験の「今日」（スタブの予約の日付と、期待する日付）は `modality_peers.today()`
  で決める。アプリと同じく設定の既定のタイムゾーン（Asia/Tokyo）の今日で、
  `date.today()`（OS のタイムゾーン。CI では UTC）は使わない。使うと JST の 0〜9 時に
  1日ずれて落ちる（`tests/modality/test_today_in_the_jst_morning.py` が時刻を固定して
  確かめる）
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
| MPPS | `tests/modality/test_mpps_scu.py` | N-CREATE・N-SET の値（予約あり・予約なし）。IN PROGRESS から COMPLETED、撮影が止まったときの DISCONTINUED、相手が停止していたときにキューに残して `mpps retry` で送信する、相手が拒否する、応答なしの後の `0x0111`・`0x0110`、送信先の固定、2つの処理が同時に再送信しても重複しない、プロファイルの `services.mpps: false` |
| 統合 | `tests/integration/test_modality_flow.py` | MWL の SCP → `exam --from-worklist --send` → Storage の SCP のスタブが受信する。受信した画像の値が予約と一致する |
| Web | `tests/web/` | ページが表示される、HTMX の部分応答、ループバック以外で待ち受けて認証が無ければ起動しない、`Origin` と CSRF トークンの検証、相手から来る値（`<script>`・制御文字）のエスケープ、画面から「取得→選択→撮影→送信」の一連の流れ、ui-kit の `tokens.css` の値が [spec/12a](spec/12a_web_screens_and_cli.md) の 10.2 の表と一致し、`input.css` がその色をすべて Tailwind へつなぐこと（`tests/web/test_theme_tokens.py`） |
| 装置プロファイル | `tests/core/test_device_profile.py` ほか | [spec/13](spec/13_device_profiles.md) の 10 章 |

## 5. Web 画面の静的ファイル

Web 画面の htmx・アイコン・CSS は、バージョンを固定して `app/web/static/` に置き、
commit している。利用者がこれらを用意する必要は無い。

| ファイル | バージョン | 入手元 | sha256 |
|----------|------------|--------|--------|
| htmx（`app/web/static/htmx.min.js`） | v2.0.9 | GitHub の bigskysoftware/htmx の releases | `57d9191515339922bd1356d7b2d80b1ee3b29f1b3a2c65a078bb8b2e8fd9ae5f` |
| Lucide のアイコン（`app/web/static/icons/`。ISC License、同じ場所に `LICENSE`） | 1.48.0 | GitHub の lucide-icons/lucide の releases（`lucide-icons-1.48.0.zip`） | `e27a6b58bebc563581f89668a5a652782075a85a07568e4fd8051a17ce81dba6`（zip） |
| Tailwind CSS の standalone の実行ファイル（CSS を作成するときだけ） | v4.3.3 | GitHub の tailwindlabs/tailwindcss の releases | `scripts/build_css.sh` に OS ごとに固定 |
| ui-kit の CSS（`app/web/static/ui-kit/`。3 製品で共通の写し） | `VERSION` に書く | 3 製品で共通の画面の決まり（[ADR-0028](decisions/0028-shared-ui-kit-css.md)） | — |

バージョンを上げるときは、スクリプトのバージョンと sha256 を変更して実行する。
どちらのスクリプトも、sha256 が一致しなければ停止する。

```bash
bash scripts/fetch_web_assets.sh   # htmx と Lucide のアイコン
bash scripts/build_css.sh          # app/web/styles/input.css から app/web/static/app.css を作成する
```

## 6. 変更の手順

作業は `main` から作成したブランチで行い、PR でマージする。`main` に直接 commit・
push しない。1つの PR には1つの目的だけを入れる。動作を変更するときは、次の順に
更新する。各ドキュメントに何を書くかは [README.md の「書き方」](README.md#書き方)
に従う。

1. spec を更新する
2. 設計判断（方式の選択、規格が許す形式のどれを選ぶか）を伴うなら、ADR を作成する
3. テストを先に書き、コードを変更する。バグを修正するときは、再発を防ぐテストを
   先に書く
4. 使い方が変わるなら、[usage.md](usage.md) を更新する

spec に無い機能は追加しない。仕様の不明な点を推測で補って実装しない。既存の
テストに合格させるために仕様を変えない（実装を修正する）。

## 7. コーディング規約

- モジュールの依存関係は [architecture.md](architecture.md) の 2 章のとおり。
  `app/core/` は通信・ファイルの読み書き・ログ・設定ファイルに依存しない
- Python 3.10 以上で動作させ、型ヒントを付ける。PEP 8 に従う（ruff は、設定
  ファイルが無く、現在のコードに指摘が残っているため、CI にはまだ入れていない）
- データモデルは Pydantic v2
- 命名は snake_case（関数・変数）、PascalCase（クラス）、UPPER_CASE（定数）。
  マジックナンバーは定数にする
- 1ファイル 800 行以下、1関数 50 行以下を目安にする。既存のオブジェクトを変更
  せず、新しく作成するほうを選ぶ
- 依存は `requirements.txt` で管理する。標準ライブラリで済むなら外部の
  パッケージを追加しない
- 例外は [spec/08](spec/08_error_handling.md) の階層に従う。基底の例外は
  `DICOMGeneratorError` で、汎用の `Exception` や `ValueError` を直接 raise
  しない。どのレイヤーが捕捉してログに出力するかは [architecture.md](architecture.md)
  の 4 章のとおり。`except Exception:` で握りつぶさない。エラーメッセージには
  原因と文脈（入力の ID、処理の名前）を含める
- ログは [spec/09](spec/09_logging.md) に従う。`print()` ではなく `logging` を
  使う（CLI が利用者に表示する結果とエラーを除く）。`app/core/` はログを出力
  しない。患者の氏名・生年月日などの個人情報と秘密情報をログに出力しない
- CLI は [spec/04](spec/04_cli.md) に従う。結果は標準出力、エラーは標準エラー
  出力に出す。`--help` で必須の引数と使用例を示す
- 新しい機能には、正常系と異常系のテストを追加する。カバレッジは 80% 以上を
  目標にする。`app/core/` のテストでは、ファイルやネットワークを使わない

## 8. Git

- ブランチ名は `<type>/<topic>`（`feature/`・`fix/`・`refactor/`・`docs/`・
  `test/`）
- コミットメッセージは Conventional Commits の形式（`feat:`・`fix:`・
  `refactor:`・`test:`・`docs:`・`chore:`）。説明は日本語でよい。1つのコミット
  には1つの論理的な変更だけを入れる
- 秘密情報（API キー・パスワードなど）はコミットしない
- PR には、目的・変更点・確認方法・影響範囲を書く

## 9. Web 画面のキャプチャを撮り直す

usage.md の画面のキャプチャは `scripts/capture_screens.py` で撮る。架空の患者の
予約を返すワークリストの取得先と、テスト用の PACS につないだ Web 画面を起動して
おき、次を実行する。`docs/images/` に、ワークリスト・撮影・PACS・設定の画面を
幅 1280 の PNG で保存する。

```bash
pip install playwright
playwright install chromium
DTG_URL=http://127.0.0.1:8080 DTG_WEB_PASSWORD_FILE=/path/to/password.txt \
  python scripts/capture_screens.py
```

認証の無い画面なら `DTG_WEB_PASSWORD_FILE` は不要。保存した画像に、架空の患者の
値だけが写っていることを確認してからコミットする。
