# Tasks

## 1. コメントの修正

- [ ] 1.1 `app/web/styles/input.css` の冒頭のコメントからほかのプロジェクトの名前と日付を削除し、`bash scripts/build_css.sh` の後に `git diff --exit-code -- app/web/static/app.css` が差分を出さないことを確認する
- [ ] 1.2 `tests/web/test_result_wording.py` の一覧のコメントを、一覧の目的を書く形にし、`python -m pytest -q tests/web/test_result_wording.py` が合格することを確認する
- [ ] 1.3 `requirements.txt` の Web 画面の依存のコメントから承認の日付を削除し、`grep -rn -i "tsunagi\|Approved 20\|承認者" app tests scripts requirements.txt` が何も返さないことを確認する

## Workflow follow-up

- PR のレビューの後に、この change を archive する
