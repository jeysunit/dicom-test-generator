# Proposal

## Why

PACS の PIR（患者情報の事後照合）の試験で、照合の後もモダリティが仮の患者のまま同じ
Study で撮り続ける場面（IHE PIR の Case 6）を作りたい。今の DTG は、緊急の患者（予約なし）
の追加撮影を断るので、この場面を作れない。

## What Changes

- 書き終えた緊急の撮影の Study Instance UID・Study ID・患者の値を、状態の保存先の SQLite に
  記録する（止まった撮影は記録しない）
- CLI の `exam --emergency --append --study-uid <UID>` で、その記録と同じ Study・同じ患者に
  追加で撮る。患者ID か氏名が記録と違えば断る。受付番号は空のまま、シリーズは新しく作り、
  Study の日時・説明と Series Number は予約の追加撮影と同じ決まりにする
- MPPS を使うときは、追加撮影ごとに新しい MPPS の SOP Instance で N-CREATE と N-SET を送る
- 同じ緊急の Study を、別のプロセスが同時に撮らないよう、予約の撮影と同じ札で守る
- 画面は変えない（Study Instance UID を指定する欄を作らない。今の断る文言のまま）

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `exam-workflow`: 緊急の患者の追加撮影

## Impact

- コード：`app/modality/service.py`・`app/modality/queue.py`（`emergency_exams` の表。無ければ
  起動のときに作る）・`app/cli/modality_commands.py`
- 試験：`tests/modality/test_emergency_append.py`・`tests/cli/test_modality_commands.py`
- 文書：spec 12 の 6.3・8.4.1、spec 12a の CLI の表、`docs/usage.md`、ADR-0027
