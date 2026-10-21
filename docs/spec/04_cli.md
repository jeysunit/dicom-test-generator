# 04. CLI

## 概要

コマンドラインインターフェース（CLI）は、Job YAMLファイルからDICOMデータを生成し、
モダリティエミュレーター（spec/12）の操作を行う。エントリポイントは
`python -m app.cli` の1つで、引数の詳細は各コマンドの `--help` を正本とする。
この文書は、`generate`・`validate`・`quick` の仕様と、全コマンドに共通する規則
（終了コード・ログ）を定める。

**依存**: Core Engine（`app/core/`）、Service Layer（`app/services/`）

---

## コマンド構造

```bash
python -m app.cli <command> [options]
```

### サブコマンド

| コマンド | 説明 |
|---------|------|
| `generate` | Job YAMLから生成 |
| `validate` | Job YAML検証のみ |
| `quick` | 簡易生成（1コマンド） |
| `version` | バージョン表示 |
| `profiles list` | 読み込める装置プロファイルの一覧（spec/13） |
| `echo` | C-ECHO |
| `worklist query`・`worklist show` | ワークリストを取得する・1件を出力する |
| `exam` | 予約（または緊急の患者）で撮影する |
| `send` | 出力フォルダの画像を送信する |
| `queue list`・`queue retry` | 送信キューと履歴・失敗した送信の再送 |
| `commit` | 送信した検査の保管確認（Storage Commitment）を要求して待つ |
| `mpps list`・`mpps retry` | MPPS の通知のキューを出力する・失敗した通知を再送する |

`generate`・`validate`・`quick` 以外のコマンド（`echo`・`worklist`・`exam`・`send`・
`queue`・`commit`・`mpps`）の引数・出力・終了コードは、
[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の 11 章で決める。
`profiles list` と `--profile` は [13_device_profiles.md](13_device_profiles.md) が決める。

---

## generate コマンド

### 基本構文

```bash
python -m app.cli generate <job_file> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|------|------|------|
| `job_file` | ○ | Job YAMLファイルパス |

### オプション

| オプション | 短縮 | 説明 | デフォルト |
|-----------|------|------|-----------|
| `--output DIR` | `-o` | 出力ディレクトリ（Job YAML上書き） | Job YAMLの設定 |
| `--verbose` | `-v` | 詳細ログ表示 | false |
| `--quiet` | `-q` | エラー以外非表示 | false |
| `--log-file FILE` | | ログファイルパス | logs/dicom_generator.log |
| `--dry-run` | | 実行せず検証のみ | false |
| `--profile NAME` | | 装置プロファイル（Job YAML の `device_profile` を上書き。spec/13） | Job YAMLの設定 |
| `--abnormal-level L` | | 異常のデータのレベル（`none` / `mild` / `moderate` / `severe`。Job YAML の `abnormal.level` を上書き。[02](02_core_engine.md)） | Job YAMLの設定（無ければ none） |

`--verbose` と `--quiet` は同時に指定できない。

### 使用例

```bash
# 基本実行
python -m app.cli generate job.yaml

# 出力先変更
python -m app.cli generate job.yaml -o custom_output/

# 詳細ログ
python -m app.cli generate job.yaml --verbose

# ドライラン（検証のみ）
python -m app.cli generate job.yaml --dry-run
```

### 出力例（通常モード）

```text
[INFO] Loading job: job.yaml
[INFO] Validating configuration...
[INFO] Loading patient master: data/patients_master.yaml
[INFO] Loading templates: ct_generic + hospital_a
[INFO] Starting generation...
[INFO] Study: 2.25.123456789012345678901234567890
[INFO] Series 1/3: 1 images
  [████████████████████████████████████████] 1/1
[INFO] Series 2/3: 20 images
  [████████████████████████████████████████] 20/20
[INFO] Series 3/3: 20 images
  [████████████████████████████████████████] 20/20
[INFO] Generation completed
  Total Time: 4.2s
  Files Generated: 41/41
  Success Rate: 100%
  Output: output/ACC000001/
```

### 出力例（--verbose）

```text
[DEBUG] Loaded job config: GenerationConfig(job_name='...')
[DEBUG] Merged template: 1024 keys
[INFO] Generating Study UID: 2.25.123456789...
[DEBUG] Generating image 1/41
[DEBUG]   SOP UID: 2.25.111222333...
[DEBUG]   File: output/ACC000001/P000001_20240115_CT_0001.dcm
[DEBUG]   Size: 262656 bytes
...
```

補足:

- 出力ファイル連番のゼロ埋め桁数は `max(4, 総出力枚数の桁数)`
- 例: 総出力枚数が10000以上なら `00001`, `00002`, ... の形式となる

### 出力例（--quiet）

```text
(エラーがない場合は何も表示されない)
```

---

## validate コマンド

Job YAMLの検証のみを実行（DICOM生成は行わない）。

### 基本構文

```bash
python -m app.cli validate <job_file>
```

### 使用例

```bash
python -m app.cli validate job.yaml
```

### 出力例（正常）

```text
[INFO] Validating job.yaml...
[INFO] ✓ Job configuration is valid
  Patient ID: P000001
  Accession Number: ACC000001
  Series: 3
  Total Images: 41
```

### 出力例（エラー）

```text
[ERROR] Validation failed for job.yaml
  3 validation errors for GenerationConfig
  patient.patient_id
    String should have at most 16 characters
  study.study_date
    String should match pattern '^\d{8}$'
  pixel_spec.mode
    Input should be 'simple_text' or 'ct_realistic'
```

---

## quick コマンド

Job YAMLを使わず、コマンドライン引数のみで簡易生成。

### 基本構文

```bash
python -m app.cli quick [options]
```

### 必須オプション

| オプション | 短縮 | 説明 | 例 |
|-----------|------|------|-----|
| `--patient ID` | `-p` | 患者ID | P000001 |
| `--modality NAME` | `-m` | モダリティテンプレート | ct_generic |
| `--series N` | `-s` | シリーズ数 | 3 |
| `--images LIST` | `-i` | 各シリーズの画像枚数（カンマ区切り） | 1,20,20 |
| `--output DIR` | `-o` | 出力ディレクトリ | output/ |

### オプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--accession-number ACC` | Accession Number | ACC000001 |
| `--study-date DATE` | 検査日（YYYYMMDD） | 今日 |
| `--hospital NAME` | 病院テンプレート | なし |
| `--profile NAME` | 装置プロファイル（spec/13）。Transfer Syntax はプロファイルの最初のもの | なし |
| `--pixel-mode MODE` | ピクセルモード（`simple_text` / `ct_realistic`） | ct_realistic |
| `--abnormal-level L` | 異常のデータのレベル（`none` / `mild` / `moderate` / `severe`。[02](02_core_engine.md)） | none |

### 使用例

```bash
# 最小構成
python -m app.cli quick \
  -p P000001 \
  -m ct_generic \
  -s 3 \
  -i 1,20,20 \
  -o output/

# 病院テンプレート指定
python -m app.cli quick \
  -p P000001 \
  -m ct_generic \
  --hospital hospital_a \
  -s 2 \
  -i 10,10 \
  -o output/test/

# ピクセルモード指定
python -m app.cli quick \
  -p P000001 \
  -m ct_generic \
  -s 1 \
  -i 5 \
  -o output/ \
  --pixel-mode simple_text
```

---

## version コマンド

バージョン情報表示。

```bash
python -m app.cli version
```

### 出力例

```text
DICOMテストデータ生成ツール
Version: 1.1.0
Python: 3.12.3
PyDicom: 3.0.2
```

Python と PyDicom の行は、実行した環境のバージョンになる。

---

## 終了コード

| コード | 意味 |
|-------|------|
| 0 | 成功 |
| 1 | 一般エラー（生成失敗） |
| 2 | 設定エラー（Job YAML不正・modality の設定のエラー） |
| 3 | ファイルI/Oエラー |
| 4 | バリデーションエラー（予約の値を転記できない・表現できない文字を含む） |
| 5 | 通信エラー（Association を確立できない・相手が Failure を返した・タイムアウト。モダリティエミュレーターのコマンド。[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) 11.6） |

例外から終了コードへの対応は `app/cli/main.py` の `_map_exception_to_exit_code` が持つ。
例外の階層は [08_error_handling.md](08_error_handling.md) が決める。

### 使用例（シェルスクリプト）

```bash
#!/bin/bash

python -m app.cli generate job.yaml
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "Success!"
elif [ $EXIT_CODE -eq 2 ]; then
  echo "Invalid job configuration"
  exit 1
fi
```

---

## 進捗表示

画像の生成中は、`app/cli/progress.py` が tqdm の進捗バーを標準エラー出力に出す。
`--quiet` のときは出さない。

```text
 60%|████████████████        | 12/20 [00:01<00:00, 9.52img/s]
```

---

## エラー表示

`app/cli/main.py` の `main()` は、コマンドが送出した例外を1か所で捕捉し、
`[ERROR] <メッセージ>` を標準エラー出力に出して、上の終了コードで終了する。
メッセージは端末に出力する前に制御文字を可視化する
（`app/cli/terminal.py` の `sanitize_for_terminal`。
理由は [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) 11.7）。

---

## ログファイル

ログの設定は設定ファイルでなく、`app/cli/main.py` の `setup_logging` に固定してある。
出力先は各コマンドの `--log-file`（既定 `logs/dicom_generator.log`）で変える。
ローテーションは 10MB・5世代で、仕組みの詳細は [09_logging.md](09_logging.md) が決める。

```text
logs/
├── dicom_generator.log       # 現在
├── dicom_generator.log.1     # 1世代前
├── dicom_generator.log.2
├── dicom_generator.log.3
├── dicom_generator.log.4
└── dicom_generator.log.5
```

---

## 実装ガイドライン

### ファイル構成

```text
app/cli/
├── __init__.py
├── __main__.py            # python -m app.cli のエントリポイント
├── main.py                # argparse の定義・ログの設定・終了コードの対応
├── commands.py            # generate・validate・quick・profiles list・version
├── modality_commands.py   # echo・worklist・exam・send・queue・commit・mpps
├── progress.py            # 進捗表示（tqdm）
└── terminal.py            # 端末へ出す前の制御文字の処理
```

---

## テスト

テストは `tests/cli/` にある。

| ファイル | 対象 |
|---------|------|
| `test_commands.py` | generate・validate・quick |
| `test_profile_commands.py` | `profiles list`・`--profile` |
| `test_modality_commands.py` | echo・worklist・exam・send・queue |
| `test_phase3c_commands.py` | commit・mpps |
| `test_terminal.py` | 端末へ出す前の制御文字の処理 |

```python
# tests/cli/test_commands.py の形（要約）
def test_generate_command_success(tmp_path):
    args = argparse.Namespace(
        job_file=str(job_file),
        output=None,
        verbose=False,
        quiet=False,
        dry_run=False,
    )
    assert generate_command(args) == 0
```

---

## 関連文書

- [09_logging.md](09_logging.md): ログの仕組み
- [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md): モダリティエミュレーターのコマンド
- [13_device_profiles.md](13_device_profiles.md): 装置プロファイル
