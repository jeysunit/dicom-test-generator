# Tasks

## 1. コードと依存の削除

- [x] 1.1 `app/gui/` と `tests/gui/` を削除し、`grep -rn "app.gui\|app/gui\|PySide6\|pytestqt\|qtbot" app tests` が何も返さないことを確認する
- [x] 1.2 `requirements.txt` から PySide6 と pytest-qt の行を削除し、新しい venv に `pip install -r requirements.txt` で入れて PySide6 が入らないことを確認する
- [x] 1.3 `QT_QPA_PLATFORM` を設定せずに `python -m pytest -q` を実行し、すべて合格することを確認する
- [x] 1.4 `python -m app.gui` がモジュールの無いエラーで終了し、`python -m app.cli quick -p P000001 -m ct_generic -s 1 -i 3 -o <一時フォルダ>` で DICOM ファイルが 3 つ書き出されることを確認する

## 2. CI と Docker

- [x] 2.1 `.github/workflows/ci.yml` の pytest のジョブから `QT_QPA_PLATFORM` と Qt のシステムライブラリのインストールを、Docker のジョブから PySide6 が無いことの確認を削除し、PR の CI がすべて合格することを確認する
- [x] 2.2 `Dockerfile` の依存の除外から PySide6・pytest-qt を削除してコメントを直し、CI の Docker のジョブが合格することを確認する

## 3. ADR

- [x] 3.1 `docs/decisions/0022-remove-desktop-gui.md` を template.md から作成して `docs/decisions/README.md` の一覧に追加し、`python scripts/check_doc_dates.py origin/main..HEAD` が合格することを確認する
- [x] 3.2 ADR-0003・ADR-0006 の状態の行を「置き換え済み（ADR-0022）」に、ADR-0011 の状態の行に ADR-0022 が「既存の PySide6 の GUI の扱い」を置き換えたことを書き、最終更新日と一覧の状態を合わせ、本文が変わっていないことを `git diff` で確認する

## 4. ドキュメント

- [x] 4.1 `docs/spec/05_gui.md` を欠番の文書にし、`docs/README.md` の spec の表と `docs/spec/10_unused.md` を合わせ、リンクの検査で切れたリンクが無いことを確認する
- [x] 4.2 README・usage・architecture・development・project_charter・spec の 02・07・08・09・12 から、デスクトップ画面・PySide6・pytest-qt・`QT_QPA_PLATFORM` の記述を削除し、`grep -rn "PySide6\|pytest-qt\|QT_QPA\|app/gui\|デスクトップ画面" README.md AGENTS.md docs` の結果が ADR と欠番の文書だけであることを確認する
- [x] 4.3 `docs/roadmap.md` の「次に行うもの」からデスクトップ画面の削除を削除し、「未実装」に Web 画面のファイルの作成の画面を追加し、markdownlint が合格することを確認する

## Workflow follow-up

- PR のレビューの後に、この change を archive する
