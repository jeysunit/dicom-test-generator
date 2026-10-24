# Proposal

## Why

PACS・ワークリスト・撮影の画面で、表と時刻の表示に次の気になる点が残っている。

- ワークリストの「（… に取得）」と PACS の画面の時刻に、タイムゾーンの表記が無い。画面を動かす
  マシンの時刻か、利用者の手元の時刻か、読み手には分からない（#35）
- PACS の画面で、狭い画面の表を横にスクロールしても、2 秒ごとの再取得で左端に戻る（#51）
- 撮影の画面で、「撮影」を押した後にフォーカスが戻らない。最後の1行の押せない「外す」の
  理由が、マウスを乗せたときの表示にしか出ない。狭い画面でルーチンの表の右端のボタンを
  押すと、表が横に動いて先頭の列が切れる（#56）

## What Changes

- 取得の時刻と、PACS の画面の検査日時・受付日時・完了日時の見出しに、画面を動かす
  マシンの UTC からの差（`UTC+09:00`）を添える
- 再取得・再送で表を差し替えても、横にスクロールしている位置を保つ
- 撮影の応答の後は、フォーカスを結果の場所へ移す
- 最後の1行の「外す」は `aria-disabled` にし、見えない文を `aria-describedby` で結ぶ
- ルーチンの表を、幅 390px 前後でも枠の中ではみ出さない幅にする

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `worklist-screen`: 取得の時刻に UTC の差
- `image-sending`: 表の横スクロールの保持、時刻の見出しに UTC の差
- `exam-routines`: 「外す」の理由、狭い画面の表の幅、撮影の後のフォーカス

## Impact

- 画面：`app/web/static/app.js`、`app/web/styles/input.css`（`app.css` を作り直す）、
  `app/web/templates`（`_queue.html`・`_worklist_results.html`・`_routine_fields.html`・`exam.html`）、
  `app/web/display.py`、`app/web/templating.py`
- 文書：spec 12a の 10.4・10.5・10.6、`openspec/specs`
- サーバー・CLI・作る画像は変えない

## 決めた点

- 時刻は、保存している値（このマシンの時刻）を変えず、UTC からの差を添える形にした。
  利用者のブラウザの時刻に直すと、予約や画像の時刻と食い違うため
