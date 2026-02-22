# 01. アーキテクチャ設計

## アーキテクチャ概要

### レイヤー構造（重要）

```text
┌─────────────────────────────────────────────────┐
│  UI Layer                                       │
│  ┌──────────────┐  ┌──────────────┐            │
│  │   CLI        │  │   GUI        │            │
│  │  (Phase 1)   │  │  (Phase 2)   │            │
│  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                     │
├─────────┼─────────────────┼─────────────────────┤
│         ▼                 ▼                     │
│  ┌─────────────────────────────────┐           │
│  │   Service Layer                 │           │
│  │   - StudyGeneratorService       │           │
│  │   - TemplateLoaderService       │           │
│  │   - PatientLoaderService        │           │
│  │   - JobValidatorService         │           │
│  └────────────┬────────────────────┘           │
│               │                                 │
├───────────────┼─────────────────────────────────┤
│               ▼                                 │
│  ┌─────────────────────────────────┐           │
│  │   Core Engine (Phase 0)         │           │
│  │   - DICOMBuilder                │           │
│  │   - UIDGenerator                │           │
│  │   - PixelGenerator              │           │
│  │   - FileMetaBuilder             │           │
│  │   - SpatialCalculator           │           │
│  │   - AbnormalGenerator           │           │
│  └─────────────────────────────────┘           │
└─────────────────────────────────────────────────┘
```

### 設計原則

UI は Core を直接操作しない。

- 正: `CLI → Service Layer → Core Engine`
- 誤: `CLI → Core Engine` (Service Layer をバイパス)

これにより：

- Core Engine は UI 非依存（単体テスト容易）
- Service Layer で共通ロジックを集約
- CLI/GUI で同じビジネスロジックを再利用

---

## フェーズ別アーキテクチャ

### Phase 0: Core Engine（最優先）

DICOM生成ロジックの実装。

成果物:

- `app/core/` パッケージ
- 単体テスト
- Core API仕様の実装

依存関係: なし（完全独立）

完了条件:

```python
# 以下のAPIが動作すること
from app.core import DICOMBuilder, UIDGenerator

uid_gen = UIDGenerator(method="uuid_2_25")
study_uid = uid_gen.generate_study_uid()

builder = DICOMBuilder()
ds = builder.build_ct_image(
    patient_id="P000001",
    study_uid=study_uid,
    ...
)
ds.save_as("test.dcm")
```

検証方法:

- `dcmdump test.dcm` で内容確認
- 医療ビューア（Horos等）で表示確認

---

### Phase 1: CLI

コマンドラインからの生成実行。

成果物:

- `app/cli/main.py`
- Job YAML サポート
- 進捗表示

依存関係: Phase 0 Core Engine

使用例:

```bash
# Job YAMLから生成
python -m app.cli generate job.yaml

# 簡易生成（1コマンド）
python -m app.cli quick \
  --patient P000001 \
  --modality CT \
  --series 3 \
  --images 20,20,20 \
  --output output/
```

完了条件:

- Job YAMLからDICOM生成成功
- エラー時に適切な終了コードとメッセージ
- ログファイル出力

---

### Phase 2: GUI

デスクトップGUIインターフェース。

成果物:

- `app/gui/main_window.py`
- PySide6 GUI
- 非同期処理（QThread）

依存関係: Phase 0, Phase 1 Service Layer

完了条件:

- テンプレート選択
- 患者マスター読み込み
- リアルタイム進捗表示
- キャンセル機能

---

### Phase 1.5: Storage SCP（オプション）

DICOM C-STORE受信。

成果物:

- `app/scp/storage_scp.py`
- PyNetDICOM統合

依存関係: Phase 0

完了条件:

- C-STORE受信
- ファイル保存
- ログ出力

注: これはオプション機能であり、Phase 2の後に実装しても良い。

---

## コンポーネント設計

### Core Engine

```text
app/core/
├── __init__.py
├── dicom_builder.py        # DICOM Dataset構築
├── uid_generator.py         # UID生成
├── pixel_generator.py       # ピクセルデータ生成
├── file_meta_builder.py     # File Meta構築
├── spatial_calculator.py    # 空間座標計算
├── abnormal_generator.py    # 異常データ生成
└── models.py                # データモデル
```

### Service Layer

```text
app/services/
├── __init__.py
├── study_generator.py       # スタディ生成サービス
├── template_loader.py       # テンプレート読み込み
├── patient_loader.py        # 患者マスター読み込み
└── job_validator.py         # Job設定検証
```

### CLI

```text
app/cli/
├── __init__.py
├── main.py                  # CLIエントリポイント
├── commands.py              # サブコマンド定義
└── progress.py              # 進捗表示
```

### GUI

```text
app/gui/
├── __init__.py
├── main_window.py           # メインウィンドウ
├── worker_thread.py         # QThreadワーカー
├── widgets.py               # カスタムウィジェット
└── dialogs.py               # ダイアログ
```

---

## データフロー

### 生成フロー（CLI/GUI共通）

```text
1. Job設定読み込み
   ↓
2. テンプレート読み込み・マージ
   ↓
3. 患者マスター読み込み
   ↓
4. UID生成（Study/Series/Instance）
   ↓
5. 各画像について：
   a. メタデータ構築
   b. ピクセルデータ生成
   c. File Meta構築
   d. DICOM保存
   ↓
6. 完了ログ出力
```

### 詳細フロー（Core Engine内部）

```python
# StudyGeneratorService (Service Layer)
study_config = load_job_config("job.yaml")
patient = load_patient("P000001")
template = load_and_merge_templates(...)

# UIDGenerator (Core Engine)
uid_ctx = UIDContext(
    study_uid=uid_gen.generate_study_uid(),
    frame_of_reference_uid=uid_gen.generate_frame_of_reference_uid()
)

# For each series
for series_idx in range(study_config.num_series):
    series_uid = uid_gen.generate_series_uid()

    # For each instance
    for instance_idx in range(series_config.num_images):
        sop_uid = uid_gen.generate_sop_uid(allow_invalid=...)

        # Build DICOM Dataset
        ds = DICOMBuilder.build(
            patient=patient,
            study_uid=uid_ctx.study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            template=template,
            spatial=spatial_calculator.calculate(instance_idx),
            pixel_data=pixel_generator.generate(...),
            file_meta=file_meta_builder.build(...)
        )

        # Save
        ds.save_as(filepath)
```

---

## エラーハンドリング設計

### エラー伝播

```text
Core Engine:
  ↓ Raise: GenerationError
Service Layer:
  ↓ Catch & Log & Re-raise
UI Layer (CLI/GUI):
  ↓ Catch & Display & Exit
```

### 例外階層

```text
DICOMGeneratorError (Base)
├── ConfigurationError
│   ├── TemplateError
│   └── PatientDataError
├── GenerationError
│   ├── UIDGenerationError
│   ├── PixelGenerationError
│   └── FileMetaError
├── IOError
│   ├── FileWriteError
│   └── TemplateLoadError
└── ValidationError
    ├── JobSchemaError
    └── DICOMValidationError
```

詳細は [08_error_handling.md](08_error_handling.md) を参照。

---

## 依存関係管理

### 必須依存

```text
pydicom>=2.4.4
pyyaml>=6.0.1
pillow>=10.0.0
numpy>=1.24.0
pydantic>=2.0.0
```

### Phase別追加依存

Phase 1 (CLI):

```text
python-dateutil>=2.8.2
```

Phase 2 (GUI):

```text
PySide6>=6.7.0
```

Phase 1.5 (SCP):

```text
pynetdicom>=2.0.0
```

---

## テスト戦略

### Unit Tests (Phase 0)

```text
tests/core/
├── test_uid_generator.py
├── test_pixel_generator.py
├── test_file_meta_builder.py
├── test_spatial_calculator.py
└── test_dicom_builder.py
```

各コンポーネントを独立してテスト。

### Integration Tests (Phase 1)

```text
tests/integration/
├── test_study_generation.py
├── test_template_loading.py
└── test_job_execution.py
```

Service Layer + Core Engine のテスト。

### E2E Tests (Phase 2)

```text
tests/e2e/
├── test_cli_generation.py
└── test_gui_generation.py
```

実際のファイル生成を確認。

---

## パフォーマンス考慮事項

### メモリ使用量

- ピクセルデータ: 512x512x16bit = 0.5MB/画像
- 100枚生成: 約50MB

メモリ問題なし。

### 生成速度目標

- 1画像: <100ms
- 100画像: <10秒

並列化は不要（GUIの非同期処理で十分）。

---

## セキュリティ考慮事項

### 入力検証

- Job YAML: Pydanticでスキーマ検証
- 患者マスター: ファイルパス検証
- テンプレート: YAMLパース前の検証

### ファイル出力

- ディレクトリトラバーサル防止
- 上書き確認（オプション）

### 機密情報

- 患者データ: ダミーデータのため機密性なし
- ログ: Patient IDなど含まれるが、テスト環境用途

---

## 将来拡張

Phase 3以降の候補：

- [ ] Web UI（FastAPI + React）
- [ ] バッチ生成（複数患者・複数検査）
- [ ] テンプレート作成支援ツール
- [ ] Query/Retrieve対応
- [ ] 他モダリティ追加（MR, CR, DX, US等）

---

## ADR参照

設計判断の詳細は以下を参照：

- [ADR-0001: Core Library First](../adr/0001-core-library-first.md)
- [ADR-0002: YAML Job Configuration](../adr/0002-yaml-job-configuration.md)
- [ADR-0003: PySide6 GUI](../adr/0003-pyside6-gui.md)
- [ADR-0006: Threading Model](../adr/0006-threading-model.md)
