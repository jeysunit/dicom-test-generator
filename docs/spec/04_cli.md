# 04. CLI

コマンドラインインターフェース（CLI）のうち、`generate`・`validate`・`quick` の
仕様と、全コマンドに共通する規則（終了コード・エラーの表示・ログ）を定める。
引数の詳細は各コマンドの `--help` を正本とする。

## 1. コマンドの一覧

エントリポイントは `python -m app.cli <command> [options]` の1つ。

| コマンド | 説明 |
|---------|------|
| `generate` | Job YAML から作成する |
| `validate` | Job YAML を検証する（作成しない） |
| `quick` | Job YAML を使わず、引数だけで作成する |
| `version` | バージョンを表示する |
| `profiles list` | 読み込める装置プロファイルの一覧 |
| `echo` | C-ECHO |
| `worklist query`・`worklist show` | ワークリストを検索する・1件を出力する |
| `exam` | 予約（または緊急の患者）で撮影する |
| `send` | 出力フォルダの画像を送信する |
| `queue list`・`queue retry` | 送信キューと履歴・失敗した送信の再送信 |
| `commit` | 送信した検査の保管確認（Storage Commitment）を要求して待つ |
| `mpps list`・`mpps retry` | MPPS の通知のキューを出力する・失敗した通知を再送信する |

- `generate`・`validate`・`quick`・`version` 以外のモダリティエミュレーターの
  コマンド（`echo`・`worklist`・`exam`・`send`・`queue`・`commit`・`mpps`）の
  引数・出力・終了コードは、[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md)
  の 11 章で定める
- `profiles list` と `--profile` は [13_device_profiles.md](13_device_profiles.md)
  で定める

## 2. generate

```bash
python -m app.cli generate <job_file> [options]
```

### 2.1 引数とオプション

| 引数・オプション | 短縮 | 説明 | 既定値 |
|-----------|------|------|-----------|
| `job_file` | | Job YAML のファイルのパス（必須） | |
| `--output DIR` | `-o` | 出力ディレクトリ（Job YAML の `output_dir` を上書き） | Job YAML の値 |
| `--verbose` | `-v` | コンソールに DEBUG 以上のログを出力する | false |
| `--quiet` | `-q` | コンソールに ERROR 以上のログだけを出力し、進捗バーを出さない | false |
| `--log-file FILE` | | ログファイルのパス | `logs/dicom_generator.log` |
| `--dry-run` | | Job YAML を検証するだけで、作成しない | false |
| `--profile NAME` | | 装置プロファイル（Job YAML の `device_profile` を上書き） | Job YAML の値 |
| `--abnormal-level L` | | 異常のデータのレベル（`none`・`mild`・`moderate`・`severe`。Job YAML の `abnormal.level` を上書きし、`abnormal` のほかのキーは残す。[02](02_core_engine.md) の 7 章） | Job YAML の値（無ければ `none`） |

`--verbose` と `--quiet` は同時に指定できない。

### 2.2 出力

- 作成が完了したら、標準出力に `Generation completed: <出力フォルダ>` を出力する
- ログはコンソール（標準エラー出力）とログファイルに出力する（9 章）
- 出力ファイル名の規則は [03_data_models.md](03_data_models.md) の 5 章にある
- `--dry-run` のときは、標準出力に次を出力して終了コード 0 で終わる

```text
Dry-run mode: configuration is valid.
Patient ID: P000001
Accession Number: ACC000001
Series: 3
Total Images: 41
```

## 3. validate

Job YAML を検証するだけで、DICOM は作成しない。

```bash
python -m app.cli validate <job_file>
```

検証が成功すれば、標準出力に次を出力して終了コード 0 で終わる。

```text
Job configuration is valid
Patient ID: P000001
Accession Number: ACC000001
Series: 3
Total Images: 41
```

検証が失敗すれば、Pydantic の検証エラーを `[ERROR] <メッセージ>` の形で
標準エラー出力に出力し、終了コード 4 で終わる（6・8 章）。

## 4. quick

Job YAML を使わず、コマンドラインの引数だけで作成する。

```bash
python -m app.cli quick [options]
```

### 4.1 必須のオプション

| オプション | 短縮 | 説明 | 例 |
|-----------|------|------|-----|
| `--patient ID` | `-p` | 患者ID。患者マスター（`data/patients_master.yaml`）から検索する | P000001 |
| `--modality NAME` | `-m` | モダリティテンプレート | ct_generic |
| `--series N` | `-s` | シリーズ数 | 3 |
| `--images LIST` | `-i` | 各シリーズの画像枚数（カンマ区切り） | 1,20,20 |
| `--output DIR` | `-o` | 出力ディレクトリ | output/ |

### 4.2 そのほかのオプション

| オプション | 説明 | 既定値 |
|-----------|------|-----------|
| `--accession-number ACC` | Accession Number | ACC000001 |
| `--study-date DATE` | 検査日（YYYYMMDD） | 実行した日 |
| `--hospital NAME` | 病院テンプレート | なし |
| `--profile NAME` | 装置プロファイル。Transfer Syntax はプロファイルの最初のもの | なし |
| `--pixel-mode MODE` | ピクセルモード（`simple_text`・`ct_realistic`・`phantom`。[06](06_dicom_rules.md) の 4 章） | ct_realistic |
| `--abnormal-level L` | 異常のデータのレベル（`none`・`mild`・`moderate`・`severe`。[02](02_core_engine.md) の 7 章） | none |

### 4.3 動作

- 患者ID が患者マスターに無い、テンプレートが無い、`--series` と `--images`
  の件数が一致しない、`--images` に正の整数以外がある、`--pixel-mode` が
  上の3つ以外のときは、設定エラー（終了コード 2）
- 検査時刻は実行した時刻。UID は UUID 2.25 方式、文字セットと
  Transfer Syntax（`--profile` が無いとき）は既定値を使う
- 進捗バーは出さない。`--verbose`・`--quiet`・`--log-file` は無く、ログは
  既定のログファイルとコンソール（INFO 以上）に出力する
- 作成が完了したら、標準出力に `Generation completed: <出力フォルダ>` を出力する

## 5. version

```bash
python -m app.cli version
```

```text
DICOMテストデータ生成ツール
Version: 1.2.0
Python: 3.12.3
PyDicom: 3.0.2
```

Version は git のタグから作った版で、タグの上は `1.2.0`、タグより後は
`1.2.0+37.g60970f9`、不明は `0.0.0+unknown`
（[development.md](../development.md) の 10 章）。
Python と PyDicom の行は、実行した環境のバージョンになる。

## 6. 終了コード

| コード | 意味 | 例外 |
|-------|------|------|
| 0 | 成功 | |
| 1 | 一般エラー（作成の失敗） | 2〜5 の例外以外の `DICOMGeneratorError` とそのほかの例外 |
| 2 | 設定エラー（Job YAML の構文エラー・テンプレート・装置プロファイル・患者マスターのエラー、modality の設定のエラー） | `ConfigurationError`・`ModalityConfigError` |
| 3 | ファイル I/O のエラー（Job YAML が無いなど） | `IOError`（`app.core.exceptions`） |
| 4 | バリデーションエラー（Job YAML の値の検証エラー・予約の値を転記できない・表現できない文字を含む） | `ValidationError`（Pydantic と `app.core.exceptions`）・`WorklistMappingError` |
| 5 | 通信エラー（Association を確立できない・相手が Failure を返した・タイムアウト。[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の 11.6） | `AssociationError`・`WorklistQueryError`・`StoreError`・`StorageCommitmentError`・`MPPSError` |

例外から終了コードへの対応は `app/cli/main.py` の `_map_exception_to_exit_code`
が持つ。例外の階層は [08_error_handling.md](08_error_handling.md) で定める。

## 7. 進捗の表示

`generate` で画像を作成している間は、`app/cli/progress.py` が tqdm の進捗バーを
標準エラー出力に出す。`--quiet` のときは出さない。

```text
 60%|████████████████        | 12/20 [00:01<00:00, 9.52img/s]
```

## 8. エラーの表示

`app/cli/main.py` の `main()` は、コマンドが送出した例外を1か所で捕捉し、
`[ERROR] <メッセージ>` を標準エラー出力に出して、6 章の終了コードで終了する。
メッセージは端末に出力する前に制御文字を可視化する
（`app/cli/terminal.py` の `sanitize_for_terminal`。
理由は [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の 11.7）。

## 9. ログファイル

ログの設定は設定ファイルでなく、`app/cli/main.py` の `setup_logging` に固定
してある。

| 出力先 | レベル |
|--------|--------|
| ログファイル | DEBUG 以上 |
| コンソール（標準エラー出力） | INFO 以上。`--verbose` なら DEBUG 以上、`--quiet` なら ERROR 以上 |

- 形式は `[%(levelname)s] %(asctime)s - %(message)s`。コンソールでは制御文字を
  可視化する
- ログファイルのパスは `--log-file`（既定 `logs/dicom_generator.log`）で変更する
- ローテーションは 10MB・5 世代（`dicom_generator.log.1`〜`.5`）。仕組みの詳細は
  [09_logging.md](09_logging.md) で定める

## 10. ファイル構成

```text
app/cli/
├── __init__.py
├── __main__.py            # python -m app.cli のエントリポイント
├── main.py                # argparse の定義・ログの設定・終了コードの対応
├── commands.py            # generate・validate・quick・profiles list・version
├── modality_commands.py   # echo・worklist・exam・send・queue・commit・mpps
├── progress.py            # 進捗の表示（tqdm）
└── terminal.py            # 端末へ出す前の制御文字の処理
```

## 11. テスト

テストは `tests/cli/` にある。

| ファイル | 対象 |
|---------|------|
| `test_commands.py` | generate・validate・quick |
| `test_profile_commands.py` | `profiles list`・`--profile` |
| `test_modality_commands.py` | echo・worklist・exam・send・queue |
| `test_phase3c_commands.py` | commit・mpps |
| `test_terminal.py` | 端末へ出す前の制御文字の処理 |

## 12. 関連する文書

- [09_logging.md](09_logging.md)：ログの仕組み
- [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md)：モダリティエミュレーターのコマンド
- [13_device_profiles.md](13_device_profiles.md)：装置プロファイル
