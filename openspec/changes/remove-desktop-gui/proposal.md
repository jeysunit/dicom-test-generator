# Proposal

## Why

PySide6 のデスクトップ画面（`app/gui/`）は、ADR-0011 で凍結して以来、機能を
追加していない。画面の操作は Web 画面、ファイルの作成は CLI（`generate`・`quick`）で
できるので、画面を2種類保守する理由が無い。PySide6 は大きなパッケージで、CI でも
Qt のためのシステムライブラリと offscreen の設定が要る。削除して、ファイルの作成は
CLI に任せる。

## What Changes

- **BREAKING** デスクトップ画面（`python -m app.gui`）を削除する。`app/gui/` と、
  画面のテスト（`tests/gui/`）を削除する
- `requirements.txt` から PySide6 と pytest-qt を削除する
- CI から Qt のための設定（`QT_QPA_PLATFORM`、システムライブラリのインストール、
  Docker のイメージに PySide6 が無いことの確認）を削除する。Dockerfile の
  依存の除外から PySide6・pytest-qt を削除する
- 新しい ADR「PySide6 のデスクトップ画面を削除し、ファイルの作成は CLI に任せる」を
  追加する。ADR-0003（PySide6 GUI）と ADR-0006（GUI のスレッドの方式）を置き換え済みに
  し、ADR-0011 の「既存の PySide6 の GUI の扱い」の削除の条件を置き換える
- `docs/spec/05_gui.md` を欠番にし、画面に触れているドキュメント（README・usage・
  architecture・development・project_charter・roadmap・spec の 07・08・09・10・12）
  から削除する。Web 画面にファイルの作成の画面を追加することは、roadmap の未実装に
  書く

## Capabilities

### New Capabilities

- `user-interfaces`: 利用者が DTG を操作する手段（CLI と Web 画面）と、それぞれで
  できること

### Modified Capabilities

（なし。`openspec/specs/` にはまだ spec が無い）

## Impact

- コード：`app/gui/`（Python のファイル 10 本）と `tests/gui/`（5 ファイル）を削除する。ほかのモジュールは
  `app/gui/` を import していない
- 依存：`requirements.txt` から PySide6・pytest-qt を削除する
- CI：`.github/workflows/ci.yml` の pytest のジョブと Docker のジョブ、`Dockerfile`
- ドキュメント：`README.md`・`docs/` の上に挙げたファイル、ADR の 0003・0006・0011・
  一覧、新しい ADR-0022
- 利用者：`python -m app.gui` が使えなくなる。ファイルの作成は
  `python -m app.cli generate`・`quick` で行う
