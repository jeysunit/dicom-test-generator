# user-interfaces Specification

## Purpose

利用者が DTG を操作する手段を定める。DICOM ファイルの作成は CLI で、撮影と送信は
CLI と Web 画面で行い、デスクトップ画面は提供しない。

## Requirements

### Requirement: 通信の失敗と認証切れを操作の結果に知らせる

HTMX の要求が通信で失敗したときは「サーバーに届きませんでした。接続を確かめてから、
もう一度押してください」を、401 のときは「ログインが切れました。ページを読み込み直して、
ログインし直してください」を表示しなければならない（SHALL）。401 の応答は
差し替えてはならない（SHALL NOT）。表示先は form・button・target を使う共通の
関数で決め、撮影は結果、送信は送信の結果、再送信は表の上、C-ECHO は押した行に出す。
装置の切り替えは情報バー、ルーチンの描き直しは選択のそばに同じ文言を出す。

#### Scenario: C-ECHO の要求が届かない

- **WHEN** PACS の行で C-ECHO を押し、通信が失敗する
- **THEN** その行の結果にエラーの知らせが出る

#### Scenario: 認証が切れる

- **WHEN** 撮影・送信・再送信・C-ECHO の要求が 401 になる
- **THEN** 生の応答で差し替えず、操作の結果の場所にログインの知らせを出す

#### Scenario: 装置かルーチンの変更で認証が切れる

- **WHEN** 装置の切り替えかルーチンの描き直しが 401 になる
- **THEN** 情報バーかルーチンの選択のそばにログインの知らせが出る

### Requirement: DICOM ファイルの作成は CLI で行う

DTG は、Job YAML からの作成（`generate`）と、引数だけでの作成（`quick`）を CLI で
提供しなければならない（SHALL）。作成した DICOM ファイルは指定した出力フォルダに
書き出し、成功したら終了コード 0 で終了する。

#### Scenario: Job YAML から作成する

- **WHEN** 利用者が `python -m app.cli generate <Job YAML> -o <出力フォルダ>` を実行する
- **THEN** 出力フォルダに DICOM ファイルが書き出され、終了コードは 0 になる

#### Scenario: 引数だけで作成する

- **WHEN** 利用者が `python -m app.cli quick -p <患者ID> -m <テンプレート> -s 1 -i 3 -o <出力フォルダ>` を実行する
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
