# 09. ログ

DTG が出力するログの設定と内容を定める。

## 1. 概要

- ログは Python 標準の `logging` で出力する
- **Core（`app/core/`）はログを出力しない**。ログを出力するのは Service Layer
  （`app/services/`・`app/modality/`）と、CLI・PySide6 の画面・Web 画面である
- ログの設定は設定ファイルではなく、エントリポイントのコードに固定してある。
  CLI は `app/cli/main.py` の `setup_logging`、Web 画面は
  `app/web/__main__.py` が設定する
- logger の名前は、各モジュールの `logging.getLogger(__name__)` である

## 2. ログレベル

| レベル | 用途 | 出力先（CLI） |
|--------|------|---------------|
| DEBUG | 詳細な情報 | ファイルだけ（`--verbose` ならコンソールにも） |
| INFO | 通常の動作 | ファイルとコンソール |
| WARNING | 警告（処理は続ける） | ファイルとコンソール |
| ERROR | エラー（処理は停止する） | ファイルとコンソール |

コンソールの下限は、既定が INFO、`--verbose` が DEBUG、`--quiet` が ERROR。
ファイルには常に DEBUG 以上を記録する。

## 3. CLI

### 3.1 設定

`setup_logging(verbose, quiet, log_file)` が、サブコマンドの実行の前に
root logger を設定する。

| 項目 | 内容 |
|------|------|
| ファイルの場所 | `--log-file`（既定 `logs/dicom_generator.log`）。親のフォルダが無ければ作成する |
| ファイルのハンドラ | `RotatingFileHandler`（UTF-8）。レベルは DEBUG |
| コンソールのハンドラ | `StreamHandler`（標準エラー出力）。レベルは 2 章のとおり |
| 書式 | `[%(levelname)s] %(asctime)s - %(message)s` |
| 端末への出力 | `TerminalSafeFormatter`（`app/cli/terminal.py`）を経由する。相手から来た値に含まれる制御文字を見える形（`\x1b` など）にし、端末の表示やタイトルを書き換えられないようにする |

- `--log-file` と `--verbose` は、`generate` のほか、モダリティエミュレーターの
  コマンドにもある。`--quiet` は `generate` だけが持つ
- モダリティエミュレーターのコマンドは、`--verbose` のとき pynetdicom の
  ログを DEBUG にする。既定は WARNING 以上だけを出力する

### 3.2 ローテーション

ファイルが 10MB を超えたら切り替え、5 世代まで残す。

```text
logs/
├── dicom_generator.log       # 現在のログ
├── dicom_generator.log.1     # 1 世代前（最新）
├── ...
└── dicom_generator.log.5     # 5 世代前（最古）
```

## 4. Web 画面

`python -m app.web` は `logging.basicConfig` で INFO 以上を標準エラー出力に
出す（書式は `%(asctime)s %(levelname)s %(name)s %(message)s`）。ファイルには
書き込まない。pynetdicom のログは WARNING 以上だけを出力する。

## 5. 出力するログ

### 5.1 生成（`StudyGeneratorService`）

| 時点 | レベル | 内容 |
|------|--------|------|
| 開始 | INFO | `Generation started: job_name=... patient_id=... total_images=... output_dir=...` |
| 装置プロファイルを使うとき | INFO | `Device profile: <名前>` |
| 異常のデータのレベルが `none` 以外のとき | WARNING | `Abnormal data injection is enabled: level=...` |
| 完了 | INFO | `Generation completed: patient_id=... generated=... output_dir=...` |
| `DICOMGeneratorError` で失敗 | ERROR | `Generation failed: patient_id=... output_dir=...`（Traceback つき） |
| それ以外の例外で失敗 | ERROR | `Generation failed unexpectedly: patient_id=... output_dir=...`（Traceback つき） |

`job_name` と `patient_id` は `repr()` の形（引用符つき）で出力する。画像ごとの
ログは出力しない。

### 5.2 PySide6 の画面

`GeneratorWorker` は、生成の例外を ERROR で記録する
（`Generation error: ...`・`Unexpected error: ...`。Traceback つき。spec/08 の
2.3）。

### 5.3 モダリティエミュレーター（`app/modality/`）

通信の開始・終了・相手の Status の値・件数を INFO で記録する（C-ECHO・C-FIND・
C-STORE・保管確認・MPPS・送信キュー）。相手の応答が不正なとき、再送や拒否の
ときは WARNING。詳細は [12_modality_emulator.md](12_modality_emulator.md) の
13 章にある。

### 5.4 出力しない値

患者の氏名・生年月日はログに出力しない（[README.md](../README.md) の
「コーディング規約」）。出力するのは、患者 ID・予約のキー・受付番号・
SOP Instance UID まで。表現できない文字で停止したときも、その文字はログに
出さない（spec/06 の 7.4）。

## 6. テスト

| テスト | 対象 |
|--------|------|
| `tests/cli/test_terminal.py` | 端末への出力の制御文字の処理、`setup_logging` |
| `tests/services/test_study_generator.py` | 生成のログの内容 |
| `tests/services/test_study_generator_job_charset.py` | 表現できない文字をログに出さないこと |
