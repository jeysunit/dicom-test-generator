# Proposal

## Why

画面の表示の2つの誤りを直す。

1. **依頼医が表示されない。** ワークリストの C-FIND は Requesting Physician
   (0032,1032) を返却を求める値に入れている（spec 12 の 5.2、IHE RAD TF-2 Table
   4.5-3）が、DTG は応答の値を予約に読み込まず、予約の詳細にも出していない。詳細に
   ある「紹介医」は Referring Physician's Name (0008,0090) で、正しい対応である。
   (0032,1032) は「Imaging Service Request を依頼した医師」（PS3.3 C.4.12）なので
   「依頼医」、(0008,0090) は「患者の紹介医」（PS3.3 C.7.2.1）なので「紹介医」と
   表示する
2. **送信キューの表の受付番号が空になる。** 画像には受付番号が入っているのに、
   PACS の画面の送信キューの表の受付番号の欄が「—」になる。原因は、
   `ModalityService.send`（`app/modality/service.py:659`）が `SendQueue.add_job` に
   受付番号を渡しておらず、件の受付番号が空のまま記録されること。表の受付番号は
   この記録から表示している

## What Changes

- ワークリストの応答から Requesting Physician (0032,1032) を読み込み、予約の詳細に
  「依頼医」の行を足す。「紹介医」の行は Referring Physician's Name (0008,0090) の
  まま残す。氏名の `^` は、ほかの氏名と同じく空白にして表示する
- 送信キューの件を作るとき、フォルダの最初の画像の Accession Number (0008,0050) を
  読んで記録する。画面からの送信・CLI の `send` の両方に効く
- 受付番号が空の記録の件（この変更の前に作った件）は、表示のときに画像から読んで
  表示する。画像の受付番号も空（緊急の患者）なら「—」を表示する

## Capabilities

### New Capabilities

- `worklist-screen`: Web 画面のワークリストの取得・選択・取得し直しと、その知らせ
  （`fix-worklist-refresh` と同じ capability）
- `image-sending`: 撮影した画像の送信・送信キュー・再送と、その表示
  （`resend-sent-images` と同じ capability）

### Modified Capabilities

（なし）

## Impact

- `app/core/models.py`（`WorklistItem` に依頼医）、`app/core/worklist_mapping.py`
  （応答から読む）、`app/web/templates/_worklist_detail.html`
- `app/modality/service.py`（件を作るときに受付番号を読む・表示のときの補い）
- 画像への転記は変えない（Requesting Physician は画像に転記しない。spec 12 の 6.2）
- spec：12 の 5.2・8.2、12a の 10.4・10.6
- テスト：`tests/core/`、`tests/modality/`、`tests/web/`
