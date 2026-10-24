# Proposal

## Why

公開しているリポジトリのコードのコメントと文書に、ほかのプロジェクトの名前、
開発のやり取りの記録（誰がいつ指摘・承認したか、札の番号）が残っている。読む人には
意味が無く、ほかのプロジェクトの存在を外に出すことにもなるので、一般の言い方に直す。

## What Changes

- `app/web/styles/input.css` の冒頭のコメントから、色と文字の値の出典にしたほかの
  プロジェクトの名前と日付を削除する。値の正本が docs/spec/12a の 10.2 の表であることは
  残す
- `tests/web/test_result_wording.py` の、画面に出さない言い方の一覧のコメントを、
  誰がいつ指摘したかではなく、何のための一覧かを書く形にする
- `requirements.txt` の Web 画面の依存のコメント、`tests/` のコメント、ADR-0011 から、
  承認の日付と札の番号を削除する
- 過去の OpenSpec の change（archive）にある「承認者」を「依頼者」に直す

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

（なし。コメントと文書だけの変更で、動作は変わらないので `skip_specs: true` にする）

## Impact

- コメントと文書だけの変更。`app/web/static/app.css` はコメントを含まないので、作成し直しても
  変わらない（CI の「web CSS is up to date」で確認する）
- テストの中身（一覧の言葉）は変えない
