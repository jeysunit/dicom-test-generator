# Proposal

## Why

今の使い方は Python の環境を作るところから始まり、Docker のイメージは利用者が
自分でビルドする。テストの相手（PACS・RIS）を用意する利用者はコンテナに慣れている
ことが多いので、公開したイメージを取得して起動する形を主にし、始めるまでの手順を
減らす。

## What Changes

- タグ（`v*`）の push のときだけ動く GitHub Actions の workflow を追加し、イメージを
  `ghcr.io/jeysunit/dicom-test-generator` に公開する（`<版>` と `latest` のタグ）。
  `main` への push と PR では公開しない
- イメージの中の設定ファイルは、Web 画面を全アドレス（`0.0.0.0`）で待ち受ける形にする。
  パスワードのファイルが無ければ起動しない今の動作はそのまま
- イメージの書き込むフォルダ（`logs`・`modality_state`・`output`）を、どの利用者でも
  書き込める形にする。`docker run --user "$(id -u):$(id -g)"` で動かすと、マウントした
  出力フォルダのファイルがホストの利用者のものになる
- README のクイックスタートを Docker（イメージの取得と起動・ファイルの作成）にする。
  usage.md は Docker から始め、CLI の例も Docker で実行する形にする。Python の環境での
  起動は development.md に移す
- ADR を追加する（Docker のイメージを主な配布の形にし、タグの push のときに GHCR に
  公開する）

## Capabilities

### New Capabilities

- `container-image`: 公開する Docker のイメージの内容と、公開の条件、コンテナでの
  Web 画面の待ち受けと実行する利用者

### Modified Capabilities

（なし）

## Impact

- CI：`.github/workflows/publish.yml` を追加する。`ci.yml` の Docker のジョブは、
  イメージの中の設定のまま Web 画面を確認し、`--user` で出力フォルダに書き込めることを
  確認する形にする
- `Dockerfile`：設定ファイルの `web.bind_address` を `0.0.0.0` にする。書き込む
  フォルダの権限を変える
- ドキュメント：README・usage・development・roadmap、新しい ADR-0023
- 公開：この change はタグを push しない。最初の公開（タグの push）は、承認の後に
  別に行う。workflow が `GITHUB_TOKEN` で作るパッケージは、リポジトリの公開・非公開を
  引き継ぐ（GitHub の公式の文書）。最初の公開の後に、パッケージが公開になっていることを
  確認する
