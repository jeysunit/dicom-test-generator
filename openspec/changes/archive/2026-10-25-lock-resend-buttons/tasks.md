# Tasks

## 1. 画面

- [x] 1.1 すべての「再送」と「失敗をすべて再送」の `hx-disabled-elt` を同じ指定（`#queue [data-resend], #retry-failed`）にし、「失敗をすべて再送」に `id="retry-failed"` を付ける（`_queue.html`・`pacs.html`）

## 2. 確かめ

- [x] 2.1 `tests/web/test_resend_lock.py` に、ボタンの指定がそろっていることと、「失敗をすべて再送」をサーバーが断ったとき表を残して理由が表の上に出ることの試験を足す
- [x] 2.2 手元の 127.0.0.1 の画面で、Playwright で、再送の応答を待つ間にすべての「再送」と「失敗をすべて再送」が押せなくなり、応答の後に押せる形に戻ることを確かめる
- [x] 2.3 spec 12a の 10.6 と `openspec/specs/image-sending` を直し、`python -m pytest -q` と markdownlint が合格することを確かめる
