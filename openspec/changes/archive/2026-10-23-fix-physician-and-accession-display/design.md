# Design

## Context

- 依頼医：`app/modality/worklist_scu.py` の返却を求める値に `RequestingPhysician`
  がある。`app/core/worklist_mapping.py` は `ReferringPhysicianName` だけを
  `referring_physician_name` に読み、`WorklistItem` に依頼医の項目は無い。
  `_worklist_detail.html` の「紹介医」は `referring_physician_name` を出している
- 受付番号：`SendQueue.add_job` は `accession_number` を受け取れるが、
  `ModalityService.send` は渡していない（`app/modality/service.py:659`）。表の受付
  番号は `jobs.accession_number` から出す。患者 ID・氏名・検査日時は、表示のときに
  フォルダの最初の画像から読んで補っている（`_read_job_summary`）

## Goals / Non-Goals

**Goals:**

- 依頼医と紹介医を、属性に合った名前で別々に表示する
- 送信キューの表に、画像の受付番号を表示する

**Non-Goals:**

- Requesting Physician を画像に転記すること（IHE RAD TF-2x Table A.1-1 の転記の
  対象に無い）
- 送信キューの記録の形の変更（列は今のまま使う）

## Decisions

1. **受付番号は、件を作るときに画像から読んで記録する。** 画面からの送信も CLI の
   `send` も同じ `send` を通るので、1か所で直せる。撮影の結果から渡す案は、CLI の
   `send` で任意のフォルダを送るときに効かないので採らない
2. **前に作った件は表示のときに補う。** 記録が空の件は、患者 ID などと同じく最初の
   画像から読む。記録を書き換える移行はしない（表示だけの問題なので）
3. **訳語。** 参考にした属性の日本語の表
   （<https://www.liberworks.co.jp/know/know_dicomTag.html>、
   <https://ja.sonicdicom.com/dicom-glossary/>、2026-10-23 に参照）は、
   (0008,0090) を「照会医師の名前」としている（前者の別の表は「依頼医氏名」）。
   (0032,1032) はどちらの表にも無い。画面では、(0032,1032) を「依頼医」、
   (0008,0090) を今の「紹介医」とし、2つを取り違えないことを優先する
4. **依頼医の値は、ほかの予約の値と同じ扱い。** 相手から来る値なので、読めない値の
   扱い・エスケープ・`^` の表示は今の氏名と同じにする
