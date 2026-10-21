# 08. エラーハンドリング

- 作成日：2026-02-22
- 最終更新日：2026-10-22

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
│   ├── ProfileError                  # 装置のプロファイル（spec/13 の 9）
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
    ├── ModalityConfigError      # modality: の節の誤り
    ├── AssociationError         # Association を張れない・断られた・切れた
    ├── WorklistQueryError       # C-FIND の失敗・時間切れ
    ├── WorklistMappingError     # 予約の値が写せない（文字・長さ・モダリティ）
    ├── StoreError               # C-STORE の失敗
    ├── StorageCommitmentError   # 保管確認の失敗・時間切れ
    └── MPPSError                # N-CREATE・N-SET の失敗
```

`ModalityError` は `ConfigurationError` などとは別の系統にする
（`ModalityConfigError` は `ConfigurationError` の子にしない）。
`app/core/exceptions.py` に置き、`app/modality/` と `app/core/` の
写し方（`worklist_mapping.py`）が使う。

階層図は `app/core/exceptions.py` と一致している。食い違えば exceptions.py が正本。

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
    
    def __init__(self, template_name: str, hint: str | None = None):
        # hint: 古い名前（装置ごとのテンプレート）で読みに来たときの案内
        # （装置のプロファイルの置き場へ。spec/13_device_profiles.md の 7.3）
        details = {"template_name": template_name}
        if hint is not None:
            details["hint"] = hint
        super().__init__(f"Template not found: {template_name}", details)

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

`app/cli/main.py` の `main()` が、コマンドの例外を1か所で受ける。
`_map_exception_to_exit_code` が、例外の型から終了コードを決め、
`[ERROR] <メッセージ>` を標準エラー出力に出す（対応は次章の表）。
メッセージは端末に出す前に制御文字を見える形に直す。

#### GUI（PySide6。凍結。spec/05）

`MainWindow` は設定を集める段階の例外を警告のダイアログで出す。
生成中の例外は `GeneratorWorker` が受け、`DICOMGeneratorError` は
「生成エラー」、それ以外は「予期しないエラー」のメッセージにして
`generation_finished(False, ...)` で UI スレッドへ渡す。

---

## 終了コード（CLI）

| コード | 意味 | 例外 |
|-------|------|------|
| 0 | 成功 | - |
| 1 | 一般エラー | GenerationError |
| 2 | 設定エラー | ConfigurationError |
| 3 | ファイルI/Oエラー | IOError |
| 4 | バリデーションエラー | ValidationError・WorklistMappingError・Pydantic の ValidationError |
| 5 | 通信エラー | AssociationError・WorklistQueryError・StoreError・StorageCommitmentError・MPPSError |

- `ModalityConfigError` は 2（設定エラー）にする
- ほかの `ModalityError`（例：最後に引いた結果に無い予約の鍵）は 1
- 上のどれでもない例外も 1

判定は上から順に行う（`app/cli/main.py` の `_map_exception_to_exit_code`）。
`ModalityError` 系は `ConfigurationError` などの子でないので、重ならない。

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
raise TemplateNotFoundError("mr_head_generic")
# => "Template not found: mr_head_generic (template_name=mr_head_generic)"
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

キャンセルがあるのは PySide6 の画面だけで、扱いは [05_gui.md](05_gui.md) の
「非同期処理」の節が決める。

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
# tests/services/ の形
def test_service_wraps_unexpected_error(monkeypatch):
    # Core の DICOMBuilder が想定外の例外を投げる状況を作る
    ...
    with pytest.raises(GenerationError):
        StudyGeneratorService().generate(config)
```

例外クラスそのものの試験は `tests/core/test_exceptions.py` にある。

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

## 関連文書

- [09_logging.md](09_logging.md): ログの仕組み
- [04_cli.md](04_cli.md): 終了コード
