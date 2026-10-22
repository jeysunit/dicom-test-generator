# user-interfaces Specification

## Purpose

利用者が DTG を操作する手段を定める。DICOM ファイルの作成は CLI で、撮影と送信は
CLI と Web 画面で行い、デスクトップ画面は提供しない。

## Requirements

### Requirement: DICOM ファイルの作成は CLI で行う

DTG は、Job YAML からの作成（`generate`）と、引数だけでの作成（`quick`）を CLI で
提供しなければならない（SHALL）。作成した DICOM ファイルは指定した出力フォルダに
書き出し、成功したら終了コード 0 で終了する。

#### Scenario: Job YAML から作成する

- **WHEN** 利用者が `python -m app.cli generate <Job YAML> -o <出力フォルダ>` を実行する
- **THEN** 出力フォルダに DICOM ファイルが書き出され、終了コードは 0 になる

#### Scenario: 引数だけで作成する

- **WHEN** 利用者が `python -m app.cli quick -p <患者 ID> -m <テンプレート> -s 1 -i 3 -o <出力フォルダ>` を実行する
- **THEN** 出力フォルダに DICOM ファイルが 3 つ書き出され、終了コードは 0 になる

### Requirement: デスクトップ画面を提供しない

DTG は、デスクトップ画面（PySide6）を提供してはならない（SHALL NOT）。画面での操作は
Web 画面で行う。

#### Scenario: デスクトップ画面を起動しようとする

- **WHEN** 利用者が `python -m app.gui` を実行する
- **THEN** モジュールが見つからないエラーで終了し、画面は開かない

### Requirement: 依存に GUI のパッケージを含めない

DTG の依存（`requirements.txt`）は、PySide6 と pytest-qt を含んではならない
（SHALL NOT）。テストは Qt の表示の設定（`QT_QPA_PLATFORM`）無しで実行できる。

#### Scenario: 依存をインストールしてテストを実行する

- **WHEN** 利用者が `pip install -r requirements.txt` の後に `pytest` を実行する
- **THEN** PySide6 はインストールされず、`QT_QPA_PLATFORM` を設定しなくてもテストが
  すべて合格する
