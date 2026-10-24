# Design

## Context

検索条件の欄（`app/web/templates/worklist.html`）は、ラベル「予定の AE」と選択肢
「自分（<AE タイトル>）」「絞らない」で、送る値は `station=own`・`any`。`own` なら
`WorklistQuery.station_ae_title` に自分の AE タイトルを入れ、Scheduled Procedure
Step Sequence の (0040,0001) に入る。`any` なら長さ 0 の値を送り、全ての予約に
一致する（PS3.4 C.2.2.2.3 の Universal Matching）。

## Goals / Non-Goals

**Goals:**

- 画面の文言を、(0040,0001) で絞ることが分かる言葉にする

**Non-Goals:**

- 送る条件・既定値・「別の装置」の印の変更
- 装置の切り替え（`switch-own-station`）

## Decisions

1. **ラベルは「装置の AE タイトル」、選択肢は「この装置の AE タイトルで絞る
   （DTG_CT01）」「絞らない」。** 画面の文言はモダリティ・PACS で普通に使う言葉にし、
   説明の文は足さない。「予定の」は、選択肢の側で「この装置」と言えば要らない。
   採用しなかった案：「Scheduled Station AE Title」をそのまま出す（ほかの欄の
   ラベルは日本語で、1つだけ英語になる）
2. **詳細のパネルは行を分ける。** 今の「予定」の行は予定日時・モダリティ・AE
   タイトルを `・` でつないでいて、どれが AE タイトルか分かりにくい
