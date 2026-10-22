# Proposal

## Why

公開しているリポジトリのコードのコメントに、ほかのプロジェクトの名前と、開発の
やり取りの記録（誰がいつ指摘・承認したか）が残っている。読む人には意味が無く、
ほかのプロジェクトの存在を外に出すことにもなるので、一般の言い方に直す。

## What Changes

- `app/web/styles/input.css` の冒頭のコメントから、色と文字の値の出典にしたほかの
  プロジェクトの名前と日付を削除する。値の正本が docs/spec/12a の 10.2 の表であることは
  残す
- `tests/web/test_result_wording.py` の、画面に出さない言い方の一覧のコメントを、
  誰がいつ指摘したかではなく、何のための一覧かを書く形にする
- `requirements.txt` の Web 画面の依存のコメントから、承認の日付を削除する

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

（なし。コメントだけの変更で、動作は変わらないので `skip_specs: true` にする）

## Impact

- コメントだけの変更。`app/web/static/app.css` はコメントを含まないので、作成し直しても
  変わらない（CI の「web CSS is up to date」で確認する）
- テストの中身（一覧の言葉）は変えない
