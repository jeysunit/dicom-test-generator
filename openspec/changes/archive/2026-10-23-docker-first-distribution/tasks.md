# Tasks

## 1. イメージ

- [x] 1.1 `Dockerfile` で、イメージの中の `config/app_config.yaml` の `web.bind_address` を `0.0.0.0` に書き換え（書き換えられなければビルドを失敗させる）、`logs`・`modality_state`・`output` を `1777` にし、`docker build` が成功することを確認する
- [x] 1.2 ビルドしたイメージで、パスワード無しの起動が終了コード 2 になること、パスワードを渡すと認証の無い要求に 401・認証つきの要求に 200 を返すこと、`--user "$(id -u):$(id -g)"` で `quick` を実行するとマウントした出力フォルダに DICOM ファイルが3つ、ホストの利用者の所有で書き出されることを手元で確認する
- [x] 1.3 `.github/workflows/ci.yml` の Docker のジョブを、設定ファイルをマウントせずに Web 画面を確認し、`--user` で出力フォルダに書き出せることを確認する形にし、PR の CI が合格することを確認する

## 2. 公開の workflow

- [x] 2.1 `.github/workflows/publish.yml` を追加し（`v*` のタグの push だけで動く、権限は `contents: read`・`packages: write`、actions は SHA で固定）、`actionlint` か YAML の構文の確認で誤りが無いことを確認する
- [x] 2.2 PR と `main` への push で publish.yml が動かないことを、PR の checks に publish のジョブが出ないことで確認する

## 3. ドキュメント

- [x] 3.1 ADR-0023（Docker のイメージを主な配布の形にし、タグの push のときに GHCR に公開する）を作成して一覧に追加し、`python scripts/check_doc_dates.py origin/main..HEAD` が合格することを確認する
- [x] 3.2 README のクイックスタートを Docker（パスワードのファイルの作成、イメージの取得と Web 画面の起動、ファイルの作成）にし、markdownlint が合格することを確認する
- [x] 3.3 usage.md の 1 章を Docker から始め（公開の前の `docker build` も書く）、5.1・5.2・6・7 章の例を Docker で実行する形にし、Python の環境での起動を development.md に移し、リンクの検査で切れたリンクが無いことを確認する
- [x] 3.4 development.md の CI の章に公開の workflow を、roadmap.md の「次に行うもの」から Docker の項目を削除して最初の公開（タグの push）を書き、markdownlint が合格することを確認する

## Workflow follow-up

- PR のレビューの後に、この change を archive する
- 最初の公開（タグの push）は、承認の後に別に行う
