# Proposal

## Why

送信が失敗したときや、PACS の側でデータを消したときに備えて、同じ画像を何回でも
送り直せるようにしたい。今の制限は次のとおり。

- 撮影の画面：送信の結果を表示した後は、「送信」のボタンが消え、同じ画面から
  送り直せない（`_exam_result.html`）
- PACS の画面：「再送」は送信失敗の件にだけ出し、その件の送れていない画像だけを
  送る。送信完了の件は送り直せない（`_queue.html`、`ModalityService.retry`）
- 送信キュー：送信中にできるのは待機中と送信失敗の件だけ（`queue.py` の
  `_SENDABLE_STATUSES`）
- CLI の `send <フォルダ>` は、同じフォルダを何回でも送れる（新しい件になる）。
  回数の上限はどこにも無い

## What Changes

- PACS の画面で、送信完了の件にも「再送」を出す。送信完了の件の再送は、同じ
  フォルダの画像をすべて、同じ送信先へ、新しい件として送る。回数の上限は設けない
- 送信失敗の件の「再送」は今のまま、その件の送れていない画像だけを送る
- 撮影の画面で、送信の結果の下に「もう一度送る」（枠線のボタン）を出す
- 送り直しでは画像を作り直さない。同じファイルを送るので、SOP Instance UID・
  Series Instance UID・Study Instance UID は変わらない
- 送信中の件には「再送」を出さない（同じ件を2つの処理が同時に送らない決まりは
  今のまま）

## Capabilities

### New Capabilities

- `image-sending`: 撮影した画像の送信・送信キュー・再送と、その表示

### Modified Capabilities

（なし）

## Impact

- サービス：`app/modality/service.py`（送信完了の件から新しい件を作って送る）
- 画面：`app/web/templates/_queue.html`・`_exam_result.html`・`_send_result.html`、
  `app/web/routes/pacs.py`・`exam.py`
- CLI：`queue retry --job ID` が送信完了の件も受ける（新しい件として送る）
- spec：12 の 8.2、12a の 10.5・10.6・10.8・11.5
- 保管確認：新しい件ごとに求める（今の決まりのまま）
