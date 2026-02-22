# 仕様書再構成 - クイックスタート

## 作成済みファイル一覧

### 仕様書（spec/）

```text
spec/
├── 00_overview.md           ✅ プロジェクト概要
├── 01_architecture.md       ✅ アーキテクチャ設計
├── 02_core_engine.md        ✅ Core Engine API仕様
├── 03_data_models.md        ✅ データモデル定義
├── 04_cli.md                ✅ CLI仕様
├── 05_gui.md                ✅ GUI仕様
├── 06_dicom_rules.md        ✅ DICOM医療仕様
├── 07_job_schema.md         ✅ Job YAMLスキーマ
├── 08_error_handling.md     ✅ エラーハンドリング
├── 09_logging.md            ✅ ログ仕様
├── 10_async_processing.md   ✅ 非同期処理
└── 11_storage_scp.md        ✅ Storage SCP
```

### ADR（adr/）

```text
adr/
├── 0001-core-library-first.md     ✅ Core優先開発の判断
├── 0002-yaml-job-configuration.md ✅ YAML Job設定の判断
├── 0003-pyside6-gui.md            ✅ PySide6 GUI選定の判断
├── 0004-uuid-2-25-uid.md          ✅ UID生成方式の判断
├── 0005-pixel-modes.md            ✅ ピクセルモードの判断
└── 0006-threading-model.md        ✅ スレッディングモデルの判断
```

---

## 導入手順

### 1. ディレクトリ確認

```bash
# 作成されたファイルを確認
ls -la spec/
ls -la adr/

# 完全な仕様書v1.1も確認
ls -la DICOM_GENERATOR_SPECIFICATION_v1.1.md
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

---

## 仕様書活用方法

### 開発開始前

1. **`spec/00_overview.md`** を読む（5分）
2. **`spec/01_architecture.md`** でレイヤー構造を理解（10分）
3. **`adr/0001-core-library-first.md`** で開発順序を確認（5分）

### Phase 0 実装時

1. **`spec/03_data_models.md`** を読んでPydanticモデル定義
2. **`spec/02_core_engine.md`** を読んでCore API実装
3. **`spec/07_job_schema.md`** を参考にテストJob YAML作成
4. **`spec/06_dicom_rules.md`** でDICOM医療仕様を参照

### Phase 1 実装時

1. **`spec/04_cli.md`** を読んでCLI実装
2. **`spec/08_error_handling.md`** を参照してエラー処理実装
3. **`spec/09_logging.md`** を参照してログ実装

### Phase 2 実装時

1. **`spec/05_gui.md`** を読んでGUI実装
2. **`spec/10_async_processing.md`** を参照してQThread実装

### Phase 1.5 実装時

1. **`spec/11_storage_scp.md`** を読んでStorage SCP実装

---

## 進捗管理

### Phase 0: Core Engine

- [ ] データモデル実装（`app/core/models.py`）
- [ ] UIDGenerator実装
- [ ] PixelGenerator実装
- [ ] FileMetaBuilder実装
- [ ] SpatialCalculator実装
- [ ] DICOMBuilder実装
- [ ] AbnormalGenerator実装
- [ ] 単体テスト作成

### Phase 1: CLI

- [ ] Service Layer実装
- [ ] CLIコマンド実装
- [ ] Job YAML読み込み
- [ ] 進捗表示
- [ ] エラーハンドリング

### Phase 2: GUI

- [ ] PySide6 メインウィンドウ
- [ ] QThreadワーカー
- [ ] プログレスバー
- [ ] テンプレート選択UI

---

## 次のアクション

1. `spec/00_overview.md` を読む
2. `spec/01_architecture.md` を読む
3. `spec/02_core_engine.md` と `spec/03_data_models.md` を読む
4. データモデル実装開始（`app/core/models.py`）
5. Core Engine実装開始

---

## FAQ

**Q: 元の仕様書v1.1はどうすればいいですか？**

A: `DICOM_GENERATOR_SPECIFICATION_v1.1.md` は参照用として保持。医療DICOM仕様の詳細はこちらを参照。

**Q: ADRは全て必要ですか？**

A: 全ADR（0001-0006）は作成済みです。開発開始に必要な設計判断は網羅されています。
