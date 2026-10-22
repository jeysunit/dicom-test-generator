# container-image Specification

## Purpose

公開する Docker のイメージの内容と公開の条件、コンテナでの Web 画面の待ち受けと、コンテナを実行する利用者を定める。

## Requirements

### Requirement: タグの push のときだけイメージを公開する

リポジトリに `v` で始まるタグが push されたときだけ、イメージを `ghcr.io/jeysunit/dicom-test-generator` に公開しなければならない（SHALL）。タグは、push されたタグの版と `latest` にする。`main` への push と PR では公開してはならない。

#### Scenario: 版のタグを push する

- **WHEN** `v1.2.0` のタグが push される
- **THEN** イメージが `ghcr.io/jeysunit/dicom-test-generator:1.2.0` と `:latest` で公開される

#### Scenario: PR と main への push

- **WHEN** PR が作成される、または `main` に push される
- **THEN** イメージはビルドして確認するだけで、どのレジストリにも公開されない

### Requirement: コンテナの Web 画面は全アドレスで待ち受け、パスワードを必須にする

イメージの中の設定ファイルは、Web 画面を `0.0.0.0` で待ち受ける形にしなければならない（SHALL）。パスワードのファイル（`DTG_WEB_PASSWORD_FILE`）が無いか空なら、Web 画面は起動せずに終了コード 2 で終了する。

#### Scenario: パスワード無しで起動する

- **WHEN** 設定ファイルをマウントせず、`DTG_WEB_PASSWORD_FILE` も渡さずにコンテナを起動する
- **THEN** コンテナは終了コード 2 で終了する

#### Scenario: パスワードを渡して起動する

- **WHEN** パスワードのファイルをマウントして `DTG_WEB_PASSWORD_FILE` で指定し、ポートを公開してコンテナを起動する
- **THEN** 認証の無い要求には 401 を、ユーザー名 `dtg` とそのパスワードの要求には 200 を返す

### Requirement: root 以外の任意の利用者で実行できる

コンテナは root 以外の利用者で動かなければならない（SHALL）。`--user` で任意の UID・GID を指定しても、ログ・予約の結果と送信キュー・出力のフォルダに書き込める。

#### Scenario: ホストの利用者で出力フォルダに書き出す

- **WHEN** `docker run --user "$(id -u):$(id -g)" -v "$PWD/output:/app/output"` で `python -m app.cli quick ... -o /app/output` を実行する
- **THEN** ホストの `output/` に DICOM ファイルが書き出され、ファイルの所有者はホストの利用者になる

#### Scenario: 利用者を指定しない

- **WHEN** `--user` を指定せずにコンテナを起動する
- **THEN** コンテナは uid 10001 の利用者で動く
