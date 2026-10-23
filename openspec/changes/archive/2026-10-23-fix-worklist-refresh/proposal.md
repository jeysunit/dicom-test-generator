# Proposal

## Why

ワークリストの画面で「取得し直す」を押すと、`Worklist item not found in the last
query: (worklist_key=, hint=run 'worklist query' first)` と表示され、取得し直せない。

原因は、ボタンが選んだ行の `key` だけを送る作りで、行を選ばなくても押せること。
「取得し直す」は `hx-include="#pick"` でフォームの値を送るが、行のラジオボタンが
どれも選ばれていなければ `key` は送られない。サーバーは `key` を既定値の空文字で
受け取り、空の鍵で最後の一覧を探して見つからず、例外の文字列（英語・内部の鍵・
CLI 向けの hint）をそのまま画面に出す。「ワークリストを取得」の直後は行が選ばれて
いないので、取得してすぐ押すと必ず起きる。

## What Changes

- 行を選ぶまで「取得し直す」を押せなくする
- サーバーでも、予約の鍵が空なら問い合わせを送らず、「予約を選んでから「取得し直す」を
  押してください」と表示する（スクリプトが無効のときや、画面以外からの要求）
- 取得し直せないときの知らせを、画面では利用者向けの日本語にする。内部の鍵
  （`worklist_key`）と CLI 向けの hint は画面に出さない。CLI の文言と終了コードは
  変えない

## Capabilities

### New Capabilities

- `worklist-screen`: Web 画面のワークリストの取得・選択・取得し直しと、その知らせ

### Modified Capabilities

（なし）

## Impact

- 画面：`app/web/templates/_worklist_results.html`（ボタン）、`app/web/static/app.js`
  （選んだら押せるようにする）、`app/web/routes/worklist.py`（空の鍵・日本語の知らせ）。
  撮影の画面（`app/web/routes/exam.py`）も、最後の一覧に無い鍵で開いたときに同じ
  知らせを使う
- サービス：`app/modality/service.py` の `find_item`・`refresh_item` が、失敗の種類を
  区別できる例外を投げる（`ModalityError` の子。CLI の終了コードは同じ）
- spec：`docs/spec/12a_web_screens_and_cli.md` の 10.4・10.8
- テスト：`tests/web/test_pages.py`、`tests/modality/test_service.py`
