# Proposal

## Why

画面の言葉に、仕様と画面、画面の中の場所どうしで、ずれが残っている。

- 撮影の結果から PACS へ送る操作を、仕様は「送る」、画面は「送信」と書き、撮影の
  ボタンは「撮影して送る」のままで、同じ操作が 2 つの言葉で出る（#43）
- 予約の詳細の「氏名」だけが、Patient's Name の生の値（`YAMADA^TARO=山田^太郎=…`）のまま
  出る。依頼医・紹介医は `^` を空白にして成分グループを ` / ` で区切っているが、並びが
  一覧の氏名（漢字が先）と逆（英字が先）になっている（#37）
- 撮影の画面の数の欄（画像数・シリーズ数）に範囲の外の数を入れて押すと、ブラウザの
  検証の文言がブラウザの言語（英語など）で出て、画面のほかの知らせとそろわない（#52）

## What Changes

- 画面の「撮影して送る」を「撮影して送信」、「もう一度送る」を「もう一度送信」にし、
  処理中の表示も「撮影して送信しています」にする。仕様（12a の 10.5・10.8、12 の 5 章、
  usage、architecture）の「送る」のボタンの名前を「送信」にそろえ、MPPS の結果の文言も
  画面に合わせる。CLI の出力と、DICOM の動詞としての「送る」は変えない
- 予約の詳細の「氏名」「依頼医」「紹介医」を、`^` と `=` を出さず、一覧の氏名と同じ
  順（漢字・かな・英字）に ` / ` で区切って出す。空なら「—」
- 画像数・シリーズ数の欄の検証の文言を日本語にする（「Scout の画像数は 1〜1000 で
  入れてください」「シリーズ数を入れてください」）

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `exam-workflow`・`image-sending`・`station-identity`: 撮影と送信のボタンの名前
- `worklist-screen`: 予約の詳細の氏名・依頼医・紹介医の並び
- `exam-routines`: 数の欄の検証の文言

## Impact

- 画面：`app/web/templates`（`_exam_actions.html`・`_send_outcome.html`・`exam.html`・
  `_routine_fields.html`・`_worklist_detail.html`）、`app/web/static/app.js`、
  `app/web/display.py`、`app/web/templating.py`
- 文書：spec 12a・12、usage・architecture、`openspec/specs`
- サーバー・CLI・作る画像は変えない

## 決めた点

依頼医・紹介医の並びは、一覧の氏名と同じ漢字・かな・英字の順にそろえた（今は英字が
先）。PACS の画面で漢字の氏名が先に見えるため。
