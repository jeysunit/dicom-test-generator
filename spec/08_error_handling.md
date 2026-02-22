# 08. エラーハンドリング仕様

## 概要

このドキュメントでは、アプリケーション全体のエラーハンドリング戦略を定義する。

---

## 例外階層

```text
DICOMGeneratorError (Base)
├── ConfigurationError
│   ├── TemplateError
│   │   ├── TemplateNotFoundError
│   │   └── TemplateParseError
│   ├── PatientDataError
│   │   ├── PatientNotFoundError
│   │   └── PatientDataInvalidError
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
└── ValidationError
    ├── JobValidationError
    └── DICOMValidationError
```

---

## 例外クラス定義

### ベース例外

```python
# app/core/exceptions.py

class DICOMGeneratorError(Exception):
    """ベース例外クラス"""
    
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message
```

### Configuration系エラー

```python
class ConfigurationError(DICOMGeneratorError):
    """設定関連エラー"""
    pass

class TemplateError(ConfigurationError):
    """テンプレート関連エラー"""
    pass

class TemplateNotFoundError(TemplateError):
    """テンプレートが見つからない"""
    
    def __init__(self, template_name: str):
        super().__init__(
            f"Template not found: {template_name}",
            {"template_name": template_name}
        )

class TemplateParseError(TemplateError):
    """テンプレートのパースエラー"""
    
    def __init__(self, template_path: str, parse_error: str):
        super().__init__(
            f"Failed to parse template: {template_path}",
            {"template_path": template_path, "error": parse_error}
        )

class PatientDataError(ConfigurationError):
    """患者マスターデータエラー"""
    pass

class PatientNotFoundError(PatientDataError):
    """患者が見つからない"""
    
    def __init__(self, patient_id: str):
        super().__init__(
            f"Patient not found: {patient_id}",
            {"patient_id": patient_id}
        )

class JobSchemaError(ConfigurationError):
    """Job YAML スキーマエラー"""
    
    def __init__(self, validation_errors: list):
        super().__init__(
            "Job configuration validation failed",
            {"errors": validation_errors}
        )
```

### Generation系エラー

```python
class GenerationError(DICOMGeneratorError):
    """生成関連エラー"""
    pass

class UIDGenerationError(GenerationError):
    """UID生成エラー"""
    
    def __init__(self, message: str, uid_type: str = None):
        super().__init__(
            message,
            {"uid_type": uid_type} if uid_type else {}
        )

class PixelGenerationError(GenerationError):
    """ピクセルデータ生成エラー"""
    
    def __init__(self, message: str, mode: str = None):
        super().__init__(
            message,
            {"mode": mode} if mode else {}
        )

class FileMetaError(GenerationError):
    """File Meta Information構築エラー"""
    pass

class DICOMBuildError(GenerationError):
    """DICOM Dataset構築エラー"""
    
    def __init__(self, message: str, tag: str = None):
        super().__init__(
            message,
            {"tag": tag} if tag else {}
        )
```

### IO系エラー

```python
class IOError(DICOMGeneratorError):
    """ファイルI/Oエラー"""
    pass

class FileWriteError(IOError):
    """ファイル書き込みエラー"""
    
    def __init__(self, filepath: str, reason: str):
        super().__init__(
            f"Failed to write file: {filepath}",
            {"filepath": filepath, "reason": reason}
        )

class FileReadError(IOError):
    """ファイル読み込みエラー"""
    
    def __init__(self, filepath: str, reason: str):
        super().__init__(
            f"Failed to read file: {filepath}",
            {"filepath": filepath, "reason": reason}
        )

class DirectoryCreateError(IOError):
    """ディレクトリ作成エラー"""
    
    def __init__(self, dirpath: str, reason: str):
        super().__init__(
            f"Failed to create directory: {dirpath}",
            {"dirpath": dirpath, "reason": reason}
        )
```

### Validation系エラー

```python
class ValidationError(DICOMGeneratorError):
    """バリデーションエラー"""
    pass

class JobValidationError(ValidationError):
    """Job設定バリデーションエラー"""
    pass

class DICOMValidationError(ValidationError):
    """DICOM検証エラー"""
    pass
```

---

## エラー伝播戦略

### レイヤー別の責務

```text
Core Engine:
  - 例外を発生させる（raise）
  - ログは出力しない（Pure関数）
  ↓
Service Layer:
  - Core Engineの例外をキャッチ
  - ログ出力
  - 必要に応じて再raise
  ↓
UI Layer (CLI/GUI):
  - Service Layerの例外をキャッチ
  - ユーザーに表示
  - 終了コード設定（CLI）またはダイアログ表示（GUI）
```

### 実装例

#### Core Engine

```python
# app/core/uid_generator.py
from .exceptions import UIDGenerationError

class UIDGenerator:
    def __init__(self, method="uuid_2_25", custom_root=""):
        if method not in ["uuid_2_25", "custom_root"]:
            raise UIDGenerationError(
                f"Invalid UID generation method: {method}",
                uid_type="configuration"
            )
        self.method = method
        self.custom_root = custom_root
```

#### Service Layer

```python
# app/services/study_generator.py
import logging
from app.core.exceptions import DICOMGeneratorError, GenerationError

logger = logging.getLogger(__name__)

class StudyGeneratorService:
    def generate_study(self, config):
        try:
            # Core Engine呼び出し
            result = core_generate(config)
            logger.info(f"Study generated successfully: {result.study_uid}")
            return result
        
        except GenerationError as e:
            logger.error(f"Generation failed: {e}")
            raise  # 再raise
        
        except DICOMGeneratorError as e:
            logger.error(f"Unexpected error: {e}")
            raise
```

#### CLI

```python
# app/cli/main.py
import sys
from app.core.exceptions import (
    ConfigurationError,
    GenerationError,
    IOError,
    ValidationError
)

def main():
    try:
        result = service.generate_from_job(job_file)
        print(f"[INFO] Generation completed: {result.output_dir}")
        sys.exit(0)
    
    except ConfigurationError as e:
        print(f"[ERROR] Configuration error: {e}", file=sys.stderr)
        sys.exit(2)
    
    except ValidationError as e:
        print(f"[ERROR] Validation error: {e}", file=sys.stderr)
        sys.exit(4)
    
    except IOError as e:
        print(f"[ERROR] I/O error: {e}", file=sys.stderr)
        sys.exit(3)
    
    except GenerationError as e:
        print(f"[ERROR] Generation failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
```

#### GUI

```python
# app/gui/main_window.py
from PySide6.QtWidgets import QMessageBox
from app.core.exceptions import DICOMGeneratorError

class MainWindow(QMainWindow):
    def on_generate_clicked(self):
        try:
            config = self.collect_config()
            result = service.generate(config)
            QMessageBox.information(self, "完了", "生成が完了しました")
        
        except ConfigurationError as e:
            QMessageBox.warning(self, "設定エラー", str(e))
        
        except GenerationError as e:
            QMessageBox.critical(self, "生成エラー", str(e))
        
        except DICOMGeneratorError as e:
            QMessageBox.critical(self, "エラー", str(e))
```

---

## 終了コード（CLI）

| コード | 意味 | 例外 |
|-------|------|------|
| 0 | 成功 | - |
| 1 | 一般エラー | GenerationError |
| 2 | 設定エラー | ConfigurationError |
| 3 | ファイルI/Oエラー | IOError |
| 4 | バリデーションエラー | ValidationError |

---

## ログレベルとエラー

| エラー種別 | ログレベル | 処理継続 |
|-----------|-----------|---------|
| ConfigurationError | ERROR | 中断 |
| TemplateError | ERROR | 中断 |
| PatientDataError | ERROR | 中断 |
| UIDGenerationError | ERROR | 中断 |
| PixelGenerationError | ERROR | 中断（画像単位） |
| FileWriteError | ERROR | 中断（画像単位） |
| ValidationError | ERROR | 中断 |
| 異常値注入（意図的） | WARNING | 継続 |

---

## エラーメッセージ設計

### 原則

1. **ユーザー視点**: 何が問題か明確に
2. **解決策提示**: 可能な場合は対処法を示す
3. **詳細情報**: デバッグに必要な情報を含める

### 良い例

```python
raise TemplateNotFoundError("fujifilm_scenaria_view_ct")
# => "Template not found: fujifilm_scenaria_view_ct (template_name=fujifilm_scenaria_view_ct)"
```

```python
raise FileWriteError(
    filepath="/output/test.dcm",
    reason="Permission denied"
)
# => "Failed to write file: /output/test.dcm (filepath=/output/test.dcm, reason=Permission denied)"
```

### 悪い例

```python
raise Exception("Error")  # ❌ 何のエラーか不明
raise ValueError("Invalid")  # ❌ 何が不正か不明
```

---

## エラーリカバリー

### 部分的失敗の扱い

**原則**: 画像単位でエラーハンドリング

```python
def generate_series(series_config):
    results = []
    errors = []
    
    for i in range(series_config.num_images):
        try:
            dcm = generate_image(i)
            dcm.save_as(filepath)
            results.append(filepath)
        
        except (PixelGenerationError, FileWriteError) as e:
            logger.error(f"Failed to generate image {i}: {e}")
            errors.append({"index": i, "error": str(e)})
            continue  # 次の画像へ
    
    if errors:
        logger.warning(f"Partial failure: {len(errors)}/{series_config.num_images} failed")
    
    return results, errors
```

### キャンセル時の扱い

```python
class GeneratorWorker(QThread):
    def run(self):
        try:
            for i in range(total):
                if self.cancel_requested:
                    logger.info(f"Cancelled by user. Generated {i}/{total} images")
                    self.generation_finished.emit(False, "Cancelled by user")
                    return
                
                generate_image(i)
        
        except DICOMGeneratorError as e:
            logger.error(f"Generation failed: {e}")
            self.generation_finished.emit(False, str(e))
```

---

## テスト

### 例外のテスト

```python
# tests/core/test_uid_generator.py
import pytest
from app.core.uid_generator import UIDGenerator
from app.core.exceptions import UIDGenerationError

def test_invalid_method_raises_error():
    with pytest.raises(UIDGenerationError) as exc_info:
        UIDGenerator(method="invalid_method")
    
    assert "Invalid UID generation method" in str(exc_info.value)
    assert exc_info.value.details["uid_type"] == "configuration"
```

### エラーハンドリングのテスト

```python
# tests/services/test_error_handling.py
def test_service_handles_core_error(mocker):
    # Core Engineをモック
    mocker.patch(
        'app.core.dicom_builder.DICOMBuilder.build',
        side_effect=DICOMBuildError("Test error")
    )
    
    service = StudyGeneratorService()
    
    with pytest.raises(GenerationError):
        service.generate_study(config)
```

---

## デバッグ支援

### 詳細情報の出力

```python
class DICOMGeneratorError(Exception):
    def to_dict(self):
        """デバッグ用辞書変換"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }
```

### ログ出力

```python
import logging
import json

logger = logging.getLogger(__name__)

try:
    result = generate()
except DICOMGeneratorError as e:
    logger.error(f"Error occurred: {json.dumps(e.to_dict(), indent=2)}")
    raise
```

---

## 次のステップ

1. [09_logging.md](09_logging.md) でログ仕様を確認
2. 例外クラス実装（`app/core/exceptions.py`）
3. エラーハンドリング実装
