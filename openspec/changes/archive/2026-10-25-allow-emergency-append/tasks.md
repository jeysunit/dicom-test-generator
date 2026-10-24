# Tasks

## 1. 実装

- [x] 1.1 `app/modality/queue.py` に緊急の撮影の記録（`emergency_exams`）を足し、`record_exam` で同じトランザクションに残す
- [x] 1.2 `app/modality/service.py` で、緊急の患者の追加撮影を Study Instance UID と患者ID・氏名で確かめて受け、記録の Study・患者の値で撮る。札は `emergency:<UID>` で取る
- [x] 1.3 CLI の `exam` に `--study-uid` を足し、`--emergency --append` のときだけ受ける

## 2. 確かめ

- [x] 2.1 `tests/modality/test_emergency_append.py` に、引き継ぐ値・新しい MPPS・断る場合（UID なし・記録に無い・患者ID・氏名・予約の UID・append なし・札）・止まった撮影・古いデータベースの試験を足す
- [x] 2.2 `tests/cli/test_modality_commands.py` に、`--study-uid` の終了コードと `--json` の試験を足す
- [x] 2.3 spec 12・12a、usage、ADR-0027 を直し、`python -m pytest -q` と markdownlint と ADR の日付の検査が合格することを確かめる
