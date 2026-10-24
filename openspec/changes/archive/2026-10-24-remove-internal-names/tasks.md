# Tasks

## 1. コメントと文書の修正

- [x] 1.1 `app/web/styles/input.css` の冒頭のコメントからほかのプロジェクトの名前と日付を削除し、`bash scripts/build_css.sh` の後に `git diff --exit-code -- app/web/static/app.css` が差分を出さないことを確認する
- [x] 1.2 `tests/web/test_result_wording.py` の一覧のコメントを、一覧の目的を書く形にし、`python -m pytest -q tests/web/test_result_wording.py` が合格することを確認する
- [x] 1.3 `requirements.txt`・`tests/`・ADR-0011 から承認の日付と札の番号を削除し、過去の change の「承認者」を「依頼者」に直す
- [x] 1.4 ほかのプロジェクトの名前と承認の記録が残っていないことを `git grep` で確認する

## Workflow follow-up

- PR のレビューの後に、この change を archive する
