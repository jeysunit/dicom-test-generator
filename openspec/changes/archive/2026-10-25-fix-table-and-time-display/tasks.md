# Tasks

## 1. 時刻

- [x] 1.1 `display.utc_offset_label` を足し、取得の時刻と PACS の時刻の見出しに添える。`tests/web/test_time_and_scroll.py` で確かめる

## 2. 表

- [x] 2.1 PACS の再取得・再送の差し替えで、横スクロールの位置を保つ（`app.js`）
- [x] 2.2 ルーチンの表を、幅 390px 前後でもはみ出さない幅にする。狭い画面では「種類」の列を出さず、Series Description の下に出す（`input.css`・`_routine_fields.html`。`app.css` を作り直す）

## 3. 撮影の画面

- [x] 3.1 撮影の応答の後に、フォーカスを `#result` へ移す
- [x] 3.2 最後の1行の「外す」を `aria-disabled` と `aria-describedby` にし、押しても動かさない。既存の試験の `disabled` の確認を、この形の確認に直す

## 4. 確かめ

- [x] 4.1 手元の 127.0.0.1 の画面で、Playwright で、幅 390・360・1280 で表がはみ出さないこと、最後の1行のボタンにフォーカスが止まり押しても外れないこと、撮影の後のフォーカス、PACS の表の横スクロールが再取得の後も保たれることを確かめる
- [x] 4.2 spec 12a と `openspec/specs` を直し、`python -m pytest -q` と markdownlint が合格することを確かめる
