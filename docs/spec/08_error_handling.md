# 08. エラーハンドリング

DTG の例外の階層と、例外から CLI の終了コード・画面の表示への対応を定める。
例外の使い方の規約（基底の例外を使う、握りつぶさない、など）は
[development.md](../development.md) の 7 章（コーディング規約）にある。

## 1. 例外の階層

### 1.1 階層

例外は `app/core/exceptions.py` にある。この節と食い違えば exceptions.py が
正本。

```text
DICOMGeneratorError
├── ConfigurationError
│   ├── TemplateError
│   │   ├── TemplateNotFoundError
│   │   └── TemplateParseError
│   ├── PatientDataError
│   │   ├── PatientNotFoundError
│   │   └── PatientDataInvalidError
│   ├── ProfileError                  # 装置プロファイル（spec/13 の 9 章）
│   │   ├── ProfileNotFoundError
│   │   ├── ProfileParseError
│   │   ├── DuplicateProfileError
│   │   └── ProfileMismatchError
│   └── JobSchemaError
│
├── GenerationError
│   ├── UIDGenerationError
│   ├── PixelGenerationError
│   ├── FileMetaError
│   └── DICOMBuildError
│
├── IOError
│   ├── FileWriteError
│   ├── FileReadError
│   └── DirectoryCreateError
│
├── ValidationError
│   ├── JobValidationError
│   └── DICOMValidationError
│
└── ModalityError（モダリティエミュレーター。spec/12）
    ├── ModalityConfigError      # modality: の節のエラー
    ├── AssociationError         # Association を確立できない・拒否された・切断された
    ├── WorklistQueryError       # C-FIND の失敗・タイムアウト
    ├── WorklistMappingError     # 予約の値を転記できない（文字・長さ・モダリティ）
    ├── StoreError               # C-STORE の失敗
    ├── StorageCommitmentError   # 保管確認の失敗・タイムアウト
    └── MPPSError                # N-CREATE・N-SET の失敗
```

- `ModalityError` は `ConfigurationError` などとは別の系統にする
  （`ModalityConfigError` は `ConfigurationError` の子にしない）。
  `app/modality/` と、`app/core/` の予約の値の転記（`worklist_mapping.py`）が
  使う
- `IOError` と `ValidationError` は組み込みの同名のクラスとは別のクラスである
- `JobSchemaError` と `JobValidationError` は定義だけで、送出する箇所は無い。
  Job YAML の検証のエラーは Pydantic の `ValidationError` のまま上がる
  （spec/07 の 4 章）

### 1.2 メッセージ

`DICOMGeneratorError` は `message` と `details`（辞書）を持つ。`str()` は
`details` があれば `message (キー=値, ...)`、無ければ `message` を返す。
`to_dict()` は `error_type`・`message`・`details` の辞書を返す。

| 例外 | `details` のキー |
|------|------------------|
| `TemplateNotFoundError` | `template_name`、古い名前のテンプレートでは `hint`（spec/13 の 7.3） |
| `TemplateParseError` | `template_path`・`error` |
| `ProfileNotFoundError` | `profile_name`・`searched` |
| `ProfileParseError` | `profile_path`・`errors` |
| `DuplicateProfileError` | `profile_name`・`paths` |
| `PatientNotFoundError` | `patient_id` |
| `UIDGenerationError` | `uid_type`（指定したときだけ） |
| `PixelGenerationError` | `mode`（指定したときだけ） |
| `DICOMBuildError` | `tag`（指定したときだけ） |
| `FileWriteError`・`FileReadError` | `filepath`・`reason` |
| `DirectoryCreateError` | `dirpath`・`reason` |

例：`Failed to write file: /output/test.dcm (filepath=/output/test.dcm,
reason=Permission denied)`

## 2. 例外の扱い

### 2.1 生成（`StudyGeneratorService`）

- 最初のエラーで生成を停止する。画像の単位で処理を続けることはしない。
  それより前に書き出した画像は残る
- `DICOMGeneratorError` は、ERROR のログ（Traceback つき）を出力してから
  そのまま再送出する
- それ以外の例外は、ERROR のログを出力してから `GenerationError`
  （`Unexpected generation error: ...`）に包んで送出する
- 出力フォルダを作成できなければ `DirectoryCreateError`、ファイルを書き出せ
  なければ `FileWriteError`

ログの内容は [09_logging.md](09_logging.md) の 3 章にある。

### 2.2 CLI

`app/cli/main.py` の `main()` が、コマンドの例外を 1 か所で受ける。
`_map_exception_to_exit_code` が、例外の型から終了コードを決め、
`[ERROR] <メッセージ>` を標準エラー出力に出す（対応は 3 章の表）。
メッセージは端末に出す前に制御文字を可視化する。

### 2.3 PySide6 の画面（spec/05）

`MainWindow` は設定を集める段階の例外を警告のダイアログで出す。
生成中の例外は `GeneratorWorker` が受け、ERROR のログを出力してから、
`DICOMGeneratorError` は「生成エラー」、それ以外は「予期しないエラー」の
メッセージにして `generation_finished(False, ...)` で UI スレッドへ渡す。
キャンセルの扱いは [05_gui.md](05_gui.md) の「非同期処理」の節にある。

### 2.4 Web 画面の起動

`python -m app.web` は、設定ファイルの読み込みとパスワードの確認で
`ConfigurationError`・`ModalityConfigError` が出れば、`[ERROR] <メッセージ>`
を標準エラー出力に出して終了コード 2 で終了する。正常に停止したときは 0。

## 3. 終了コード（CLI）

| コード | 意味 | 例外 |
|-------|------|------|
| 0 | 成功 | - |
| 1 | 一般エラー | GenerationError |
| 2 | 設定エラー | ConfigurationError |
| 3 | ファイル I/O エラー | IOError |
| 4 | 検証のエラー | ValidationError・WorklistMappingError・Pydantic の ValidationError |
| 5 | 通信エラー | AssociationError・WorklistQueryError・StoreError・StorageCommitmentError・MPPSError |

- `ModalityConfigError` は 2（設定エラー）にする
- ほかの `ModalityError`（例：最後に取得した結果に無い予約のキー）は 1
- 上のどれでもない例外も 1

判定は `ModalityConfigError`・`WorklistMappingError`・通信エラー・
`ConfigurationError`・`IOError`・`ValidationError`・Pydantic の
`ValidationError`・ほかの `DICOMGeneratorError`・それ以外の順に行う
（`app/cli/main.py` の `_map_exception_to_exit_code`）。`ModalityError` 系は
`ConfigurationError` などの子でないので、重ならない。

## 4. テスト

| テスト | 対象 |
|--------|------|
| `tests/core/test_exceptions.py` | 例外のクラス・`str()`・`to_dict()` |
| `tests/cli/test_commands.py`・`tests/cli/test_modality_commands.py` | 終了コードの対応 |

## 5. 関連文書

- [04_cli.md](04_cli.md)：終了コード
- [09_logging.md](09_logging.md)：ログ
