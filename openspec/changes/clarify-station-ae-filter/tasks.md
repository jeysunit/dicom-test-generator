# Tasks

## 1. 画面

- [x] 1.1 `tests/web/test_pages.py` に、検索条件のラベルと選択肢の文言、詳細のパネルの「予定の装置の AE タイトル」の行のテストを足し、今のコードで失敗することを確かめる
- [x] 1.2 `worklist.html` のラベルと選択肢、`_worklist_detail.html` の行を直し、テストが合格することを確かめる。送る条件（`station` の値 `own`・`any`）は変えない

## 2. spec と確かめ

- [x] 2.1 `docs/spec/12a_web_screens_and_cli.md` の 10.4 の図・本文・10.8 と、`docs/spec/12_modality_emulator.md` の 5.1 の「画面」の列を新しい文言にする
- [x] 2.2 `python -m pytest -q` と markdownlint が合格し、開発の環境の画面で文言が変わったことを確かめる
