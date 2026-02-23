# 04. CLI仕様

## 概要

コマンドラインインターフェース（CLI）は、Job YAMLファイルからDICOMデータを生成する。

**Phase**: Phase 1

**依存**: Phase 0 (Core Engine)

---

## コマンド構造

```bash
python -m app.cli <command> [options]
```

### サブコマンド

| コマンド | 説明 | Phase |
|---------|------|-------|
| `generate` | Job YAMLから生成 | 1 |
| `validate` | Job YAML検証のみ | 1 |
| `quick` | 簡易生成（1コマンド） | 1 |
| `version` | バージョン表示 | 1 |

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
[INFO] Loading templates: fujifilm_scenaria_view_ct + hospital_a
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
| `--modality NAME` | `-m` | モダリティテンプレート | fujifilm_scenaria_view_ct |
| `--series N` | `-s` | シリーズ数 | 3 |
| `--images LIST` | `-i` | 各シリーズの画像枚数（カンマ区切り） | 1,20,20 |
| `--output DIR` | `-o` | 出力ディレクトリ | output/ |

### オプション

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--accession-number ACC` | Accession Number | ACC000001 |
| `--study-date DATE` | 検査日（YYYYMMDD） | 今日 |
| `--hospital NAME` | 病院テンプレート | なし |
| `--pixel-mode MODE` | ピクセルモード | ct_realistic |

### 使用例

```bash
# 最小構成
python -m app.cli quick \
  -p P000001 \
  -m fujifilm_scenaria_view_ct \
  -s 3 \
  -i 1,20,20 \
  -o output/

# 病院テンプレート指定
python -m app.cli quick \
  -p P000001 \
  -m fujifilm_scenaria_view_ct \
  --hospital hospital_a \
  -s 2 \
  -i 10,10 \
  -o output/test/

# ピクセルモード指定
python -m app.cli quick \
  -p P000001 \
  -m fujifilm_scenaria_view_ct \
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
Python: 3.10.12
PyDicom: 2.4.4
```

---

## 終了コード

| コード | 意味 |
|-------|------|
| 0 | 成功 |
| 1 | 一般エラー（生成失敗） |
| 2 | 設定エラー（Job YAML不正） |
| 3 | ファイルI/Oエラー |
| 4 | バリデーションエラー |

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

### プログレスバー

```python
# app/cli/progress.py
from tqdm import tqdm

def show_progress(iterable, desc, total):
    """進捗バー表示"""
    return tqdm(iterable, desc=desc, total=total, unit="img")

# 使用例
for i in show_progress(range(20), "Series 1", 20):
    generate_image(i)
```

### 出力例

```text
Series 1: 100%|████████████████████████| 20/20 [00:02<00:00, 9.52img/s]
Series 2: 100%|████████████████████████| 20/20 [00:02<00:00, 9.48img/s]
```

---

## エラーハンドリング

### エラー表示

```python
# app/cli/main.py
import sys
from app.core.exceptions import DICOMGeneratorError

try:
    result = generate_from_job(job_config)
except ConfigurationError as e:
    print(f"[ERROR] Configuration error: {e}", file=sys.stderr)
    sys.exit(2)
except FileWriteError as e:
    print(f"[ERROR] Cannot write file: {e}", file=sys.stderr)
    sys.exit(3)
except DICOMGeneratorError as e:
    print(f"[ERROR] Generation failed: {e}", file=sys.stderr)
    sys.exit(1)
```

---

## ログファイル

### デフォルト設定

```yaml
# config/app_config.yaml
logging:
  level: "INFO"
  file: "logs/dicom_generator.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5
```

### ログローテーション

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
├── main.py           # エントリポイント
├── commands.py       # サブコマンド定義
├── progress.py       # 進捗表示
└── validators.py     # CLI引数検証
```

### main.py

```python
# app/cli/main.py
import argparse
import sys
from .commands import generate_command, validate_command, quick_command

def main():
    parser = argparse.ArgumentParser(
        prog='dicom-generator',
        description='DICOMテストデータ生成ツール'
    )
    
    subparsers = parser.add_subparsers(dest='command')
    
    # generate
    gen_parser = subparsers.add_parser('generate')
    gen_parser.add_argument('job_file')
    gen_parser.add_argument('-o', '--output')
    gen_parser.add_argument('-v', '--verbose', action='store_true')
    gen_parser.add_argument('-q', '--quiet', action='store_true')
    gen_parser.add_argument('--dry-run', action='store_true')
    
    # validate
    val_parser = subparsers.add_parser('validate')
    val_parser.add_argument('job_file')
    
    # quick
    quick_parser = subparsers.add_parser('quick')
    quick_parser.add_argument('-p', '--patient', required=True)
    quick_parser.add_argument('-m', '--modality', required=True)
    quick_parser.add_argument('-s', '--series', type=int, required=True)
    quick_parser.add_argument('-i', '--images', required=True)
    quick_parser.add_argument('-o', '--output', required=True)
    
    args = parser.parse_args()
    
    if args.command == 'generate':
        sys.exit(generate_command(args))
    elif args.command == 'validate':
        sys.exit(validate_command(args))
    elif args.command == 'quick':
        sys.exit(quick_command(args))
    else:
        parser.print_help()
        sys.exit(0)

if __name__ == '__main__':
    main()
```

---

## テスト

### 単体テスト

```python
# tests/cli/test_commands.py
def test_generate_command_success(tmp_path):
    job_file = tmp_path / "job.yaml"
    job_file.write_text("""
    job_name: "test"
    output_dir: "output"
    patient: {...}
    """)
    
    args = argparse.Namespace(
        job_file=str(job_file),
        output=None,
        verbose=False,
        quiet=False,
        dry_run=False
    )
    
    exit_code = generate_command(args)
    assert exit_code == 0
```

---

## 次のステップ

1. [05_gui.md](05_gui.md) でGUI仕様を確認
2. Service Layer実装
3. CLI実装
