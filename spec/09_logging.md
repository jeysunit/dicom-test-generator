# 09. ログ仕様

## 概要

アプリケーション全体のロギング戦略を定義する。

---

## ログレベル

| Level | 用途 | 出力先 |
|-------|------|--------|
| DEBUG | 詳細デバッグ情報 | ファイルのみ |
| INFO | 通常の動作情報 | ファイル + コンソール |
| WARNING | 警告（処理は継続） | ファイル + コンソール |
| ERROR | エラー（処理は中断） | ファイル + コンソール |

---

## ログ設定

### 設定ファイル

```yaml
# config/app_config.yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "logs/dicom_generator.log"
  max_bytes: 10485760  # 10MB
  backup_count: 5
  format: "[%(levelname)s] %(asctime)s - %(message)s"
  date_format: "%Y-%m-%d %H:%M:%S"
```

### Python実装

```python
# app/core/logging_config.py
import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(config: dict):
    """ロギング設定"""
    logger = logging.getLogger("dicom_generator")
    logger.setLevel(getattr(logging, config['level']))
    
    # ログディレクトリ作成
    log_dir = os.path.dirname(config['file'])
    os.makedirs(log_dir, exist_ok=True)
    
    # ファイルハンドラ（ローテーション）
    file_handler = RotatingFileHandler(
        config['file'],
        maxBytes=config['max_bytes'],
        backupCount=config['backup_count'],
        encoding='utf-8'
    )
    file_handler.setFormatter(
        logging.Formatter(config['format'], config['date_format'])
    )
    logger.addHandler(file_handler)
    
    # コンソールハンドラ（INFOレベル以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(config['format'], config['date_format'])
    )
    logger.addHandler(console_handler)
    
    return logger
```

---

## ログローテーション

### ファイル構造

```text
logs/
├── dicom_generator.log       # 現在のログ
├── dicom_generator.log.1     # 1世代前（最新）
├── dicom_generator.log.2     # 2世代前
├── dicom_generator.log.3     # 3世代前
├── dicom_generator.log.4     # 4世代前
└── dicom_generator.log.5     # 5世代前（最古）
```

### ローテーション条件

- **サイズ**: 10MB超過時
- **保持数**: 最大5世代

---

## 必須ログ項目

### 生成開始時（INFO）

```text
[INFO] 2025-02-21 14:30:00 - Generation started
  Modality Template: FUJIFILM SCENARIA View CT
  Hospital Template: A病院（日本語使用）
  Patient ID: P000001
  Accession Number: ACC000001
  Study UID: 2.25.123456789...
  Series Count: 3
  Total Images: 41
  Pixel Data Mode: ct_realistic
  Transfer Syntax: Implicit VR Little Endian (1.2.840.10008.1.2)
  Character Set: ISO 2022 IR 87
  Abnormal Level: none
  Output Directory: output/ACC000001
```

### 画像生成時（DEBUG）

```text
[DEBUG] 2025-02-21 14:30:05 - Generating image 1/41
  Series UID: 2.25.987654321...
  SOP Instance UID: 2.25.111222333...
  Instance Number: 1
  Image Position: [0.0, 0.0, 0.0]
  Slice Location: 0.0
  Filepath: output/ACC000001/P000001_20240115_CT_001.dcm
```

### 異常値生成時（WARNING）

```text
[WARNING] 2025-02-21 14:30:10 - Abnormal value injected
  Tag: Patient ID (0010,0020)
  Normal Value: P000001
  Abnormal Value: INVALID_ID_STRING_OVER_16_CHARS
  Abnormal Type: VR_violation + length_exceed
```

### エラー時（ERROR）

```text
[ERROR] 2025-02-21 14:30:15 - Failed to generate DICOM file
  Filepath: output/ACC000001/P000001_20240115_CT_025.dcm
  Error: KeyError - 'patient_name' not found in template
  Exception:
    Traceback (most recent call last):
      File "app/core/dicom_builder.py", line 123, in build
        name = template['patient_module']['patient_name']
    KeyError: 'patient_name'
```

### 生成完了時（INFO）

```text
[INFO] 2025-02-21 14:35:00 - Generation completed
  Total Time: 5m 00s
  Files Generated: 41/41
  Success Rate: 100%
  Output Directory: output/ACC000001
```

### キャンセル時（INFO）

```text
[INFO] 2025-02-21 14:32:30 - Generation cancelled
  Files Generated: 15/41
  Output Directory: output/ACC000001
```

---

## ログ出力実装例

### Service Layer

```python
# app/services/study_generator.py
import logging
from datetime import datetime

logger = logging.getLogger("dicom_generator.study_generator")

class StudyGeneratorService:
    def generate_study(self, config: GenerationConfig):
        start_time = datetime.now()
        
        # 開始ログ
        logger.info("Generation started")
        logger.info(f"  Modality Template: {config.modality_template}")
        logger.info(f"  Hospital Template: {config.hospital_template}")
        logger.info(f"  Patient ID: {config.patient.patient_id}")
        logger.info(f"  Accession Number: {config.study.accession_number}")
        logger.info(f"  Total Images: {self.calculate_total_images(config)}")
        logger.info(f"  Output Directory: {config.output_dir}")
        
        try:
            # 生成処理
            result = self._generate(config)
            
            # 完了ログ
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info("Generation completed")
            logger.info(f"  Total Time: {duration}")
            logger.info(f"  Files Generated: {len(result.generated_files)}/{result.total_files}")
            logger.info(f"  Success Rate: {result.success_rate * 100:.1f}%")
            
            return result
        
        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            raise
```

### Core Engine（ログ出力しない）

```python
# app/core/uid_generator.py

class UIDGenerator:
    """Core Engineはログ出力しない（Pure関数）"""
    
    def generate_study_uid(self) -> str:
        # ログ出力なし
        return self._generate()
```

### CLI

```python
# app/cli/main.py
import logging

logger = logging.getLogger("dicom_generator.cli")

def generate_command(args):
    logger.info(f"Loading job file: {args.job_file}")
    
    try:
        config = load_job(args.job_file)
        logger.info("Job configuration loaded successfully")
        
        result = service.generate_study(config)
        logger.info("Generation completed successfully")
        
        return 0
    
    except Exception as e:
        logger.error(f"Command failed: {e}")
        return 1
```

---

## ログ検索・フィルタ

### 特定パターン検索

```bash
# エラーのみ抽出
grep '\[ERROR\]' logs/dicom_generator.log

# 特定患者のログ抽出
grep 'P000001' logs/dicom_generator.log

# 異常値生成のログ抽出
grep 'Abnormal value injected' logs/dicom_generator.log
```

### 時間範囲でフィルタ

```bash
# 特定時刻以降のログ
awk '/2025-02-21 14:30:00/,0' logs/dicom_generator.log
```

---

## 構造化ログ（将来拡張）

### JSON形式ログ

Phase 2以降で検討：

```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        return json.dumps(log_data, ensure_ascii=False)

# 使用例
logger.info(
    "Image generated",
    extra={
        "patient_id": "P000001",
        "sop_uid": "2.25.123...",
        "filepath": "output/test.dcm"
    }
)
```

**出力例**:
```json
{"timestamp": "2025-02-21 14:30:05", "level": "INFO", "logger": "dicom_generator", "message": "Image generated", "patient_id": "P000001", "sop_uid": "2.25.123...", "filepath": "output/test.dcm"}
```

---

## パフォーマンス考慮

### DEBUGログの遅延評価

```python
# ❌ 悪い例（DEBUGレベルでなくても文字列結合が実行される）
logger.debug("Generated: " + str(large_object))

# ✅ 良い例（DEBUGレベルの場合のみ評価）
logger.debug("Generated: %s", large_object)
```

### 大量ログの抑制

```python
# 画像1枚ごとにログ出力すると大量になる
# => 10枚ごとにまとめる

count = 0
for i in range(100):
    generate_image(i)
    count += 1
    
    if count % 10 == 0:
        logger.info(f"Progress: {count}/100 images generated")
```

---

## ログ管理ツール（推奨）

### ログビューア

- **GUI内蔵**: `app/gui/dialogs/log_viewer_dialog.py`
- **外部ツール**: Notepad++, VS Code, tail -f

### ログ解析

```bash
# エラー数カウント
grep -c '\[ERROR\]' logs/dicom_generator.log

# 生成成功数カウント
grep -c 'Generation completed' logs/dicom_generator.log

# 平均生成時間（Total Timeから計算）
grep 'Total Time:' logs/dicom_generator.log | awk '{print $5}'
```

---

## テスト

### ログ出力のテスト

```python
# tests/test_logging.py
import logging
from app.services.study_generator import StudyGeneratorService

def test_generation_logs_info(caplog):
    """生成時にINFOログが出力されるか"""
    service = StudyGeneratorService()
    
    with caplog.at_level(logging.INFO):
        service.generate_study(config)
    
    assert "Generation started" in caplog.text
    assert "Generation completed" in caplog.text
```

---

## 次のステップ

1. [10_async_processing.md](10_async_processing.md) で非同期処理を確認
2. ロギング設定実装（`app/core/logging_config.py`）
3. Service Layerへのログ追加
