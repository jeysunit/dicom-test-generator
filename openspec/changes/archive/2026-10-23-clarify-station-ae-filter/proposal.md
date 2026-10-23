# Proposal

## Why

ワークリストの画面の検索条件「予定の AE」（選択肢「自分（DTG_CT01）」「絞らない」）は、
Scheduled Procedure Step Sequence の中の Scheduled Station AE Title (0040,0001) で
絞り込む条件だが、ラベルからはそれが分からない。(0040,0001) は「その予約を行う
予定のモダリティの AE タイトル」（PS3.3 C.4.10）で、モダリティは自分の AE タイトルを
入れて、自分に割り当てられた予約だけを取得する（IHE RAD TF-2 Table 4.5-2、PS3.17
DD.1 の例）。ラベルを、この装置の AE タイトルで絞る条件だと分かる言葉にする。

## What Changes

- 検索条件のラベルを「予定の AE」から「装置の AE タイトル」に、選択肢を
  「この装置の AE タイトルで絞る（DTG_CT01）」「絞らない」に変える
- 予約の詳細のパネルの「予定」の行に混ざっている Scheduled Station AE Title を、
  「予定の装置の AE タイトル」の行に分ける
- 送る条件・既定値（この装置の AE タイトルで絞る）・「別の装置」の印は変えない

## Capabilities

### New Capabilities

- `worklist-screen`: Web 画面のワークリストの取得・選択・取得し直しと、その知らせ
  （`fix-worklist-refresh` と同じ capability。先に archive した側が spec を作る）

### Modified Capabilities

（なし）

## Impact

- 画面：`app/web/templates/worklist.html`、`app/web/templates/_worklist_detail.html`
- spec：`docs/spec/12a_web_screens_and_cli.md` の 10.4 の図と本文・10.8、
  `docs/spec/12_modality_emulator.md` の 5.1 の表の「画面」の列
- テスト：`tests/web/test_pages.py`
- `switch-own-station` を入れると「この装置」は画面で選んだ装置になる。この change の
  文言はそのまま使える
