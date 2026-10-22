# Tasks

## 1. 再現のテスト

- [x] 1.1 `tests/web/test_pages.py` に、`key` の無い `POST /worklist/refresh` が C-FIND を送らず、「予約を選んでから」の知らせを返し、`worklist_key` を含まないことのテストを足し、今のコードで失敗することを確かめる
- [x] 1.2 最後の一覧に無い鍵・応答に無い予約・時間切れの3つについて、画面の知らせが日本語で `worklist_key`・`worklist query` を含まないことのテストを足し、今のコードで失敗することを確かめる

## 2. 実装

- [x] 2.1 `find_item`・`refresh_item` が、失敗の種類ごとの `ModalityError` の子を投げるようにし、CLI の文言と終了コードが変わらないことを `tests/cli/` で確かめる
- [x] 2.2 `worklist_refresh` で空の鍵を問い合わせずに知らせ、例外の種類ごとに日本語の文言を出す。撮影の画面を開くとき（`exam_page`・`exam_check`）も同じ文言にする
- [x] 2.3 「取得し直す」を、行を選ぶまで押せなくする（テンプレートと `app.js`）。選んだ行のある一覧は押せる状態で描く
- [x] 2.4 `python -m pytest -q` と markdownlint（docs/development.md の確認のコマンド）が合格することを確かめる

## 3. spec

- [x] 3.1 `docs/spec/12a_web_screens_and_cli.md` の 10.4 に「行を選ぶまで押せない」と空の鍵の扱いを、10.8 の表に取得し直せないときの文言を書く

## 4. 画面での確かめ

- [x] 4.1 開発の環境の画面で、取得の直後にボタンが押せないこと、行を選んで押すと「取得し直しました」になることを確かめる
