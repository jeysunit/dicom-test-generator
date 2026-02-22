# DICOM Test Data Generator

DICOMテストデータ生成ツール

A tool to generate synthetic and abnormal DICOM datasets
for testing medical imaging systems.
Pixel data is synthetic and not intended for clinical use.

---

## 概要

**DICOM Test Data Generator** は、医療画像システム
（PACS、RIS、ビューア、画像取り込みシステムなど）の
検証・開発・デバッグ用途のために、
人工的な DICOM データを生成するツールです。

生成されるピクセルデータは人工的に作成されたものであり、実際の医療画像を表すものではありません。
そのため、個人情報を含まず、安全にテスト用途へ利用できます。

本ツールは以下のような用途を想定しています：

* DICOM取り込み機能の検証
* PACS連携テスト
* 異常データ耐性テスト
* ネットワーク通信テスト
* 医療システム開発時のデバッグ

---

## 主な特徴

### ✅ リアルなDICOMメタデータ構造

* Study / Series / Instance の階層構造
* UID生成（UUIDベース）
* 空間座標計算（マルチスライス対応）
* Transfer Syntax選択対応

### ✅ 異常データ生成機能

テスト用途のため、意図的に異常なDICOMを生成できます。

例：

* 必須タグ欠落
* VR違反
* 文字数超過
* 不正UID
* フォーマット違反

異常レベルを段階的に設定可能です。

### ✅ 日本語対応

* Specific Character Set対応
* 日本語患者名
* 多言語PN表現（Alphabetic / Ideographic / Phonetic）

### ✅ ピクセル生成モード

複数のピクセル生成モードを提供します：

* 簡易モード（テキスト表示）
* CT風モード（16bit HU値）
* 合成ピクセル（検証用途）

※いずれも実画像ではありません。

### ✅ テンプレートベース設計

* モダリティテンプレート
* 病院設定テンプレート
* YAML設定による柔軟な構成

---

## 想定利用者

* 医療システムエンジニア
* PACS開発者
* DICOM開発者
* 医療機器ソフトウェア開発者
* QA / テストエンジニア

---

## 非対象用途（重要）

本ツールは以下の用途を目的としていません：

* 診断用途
* 医療行為
* 臨床評価
* AI学習用医療画像生成

生成データは臨床利用できません。

---

## 動作環境

* Python 3.10 以上
* Windows / Linux / macOS

推奨：

* Python 3.11+

---

## インストール

```bash
git clone https://github.com/jeysun/dicom-test-generator.git
cd dicom-test-generator

# 仮想環境の作成・有効化
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 依存パッケージのインストール
pip install -r requirements.txt
```

---

## 基本的な使い方（CLI）

```bash
# Job YAMLからDICOM生成
python -m app.cli generate examples/job_minimal.yaml

# 出力先を指定して生成
python -m app.cli generate examples/job_full.yaml -o output/ --verbose

# 設定検証のみ（生成なし）
python -m app.cli validate examples/job_minimal.yaml

# CLI引数のみで簡易生成
python -m app.cli quick -p P000001 -m fujifilm_scenaria_view_ct -s 3 -i 1,20,20 -o output/

# バージョン表示
python -m app.cli version
```

Job YAML に生成条件を記述します。`examples/` に最小構成・全オプション構成のサンプルがあります。

---

## Job設定例

```yaml
job_name: "テスト生成"
output_dir: "output/test"

patient:
  patient_id: "TEST001"
  patient_name:
    alphabetic: "YAMADA^TARO"
  birth_date: "20000101"
  sex: "M"

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "120000"
  num_series: 1

series_list:
  - series_number: 1
    num_images: 10

modality_template: "fujifilm_scenaria_view_ct"
pixel_spec:
  mode: "simple_text"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: ""
  use_ideographic: false
  use_phonetic: false
```

---

## GUI（Phase 2）

デスクトップGUI実装予定。

---

## Storage SCP（Phase 1.5）

DICOM通信による受信機能を追加予定。

---

## プロジェクト構成

```text
dicom-test-generator/
├── app/
│   ├── core/           # Core Engine（データモデル、DICOM構築、UID生成等）
│   ├── services/       # Service Layer（テンプレート読み込み、患者検索、生成）
│   └── cli/            # CLI（argparse、サブコマンド、進捗表示）
├── tests/
│   ├── core/           # Core Engineテスト
│   ├── services/       # Service Layerテスト
│   └── cli/            # CLIテスト
├── spec/               # 仕様書
├── adr/                # 設計判断記録
├── docs/               # MkDocsドキュメント
├── templates/          # モダリティ・病院テンプレート（YAML）
├── data/               # 患者マスターデータ
├── examples/           # Job YAML設定例
└── README.md           # 本ファイル
```

---

## 開発方針

本プロジェクトは仕様駆動開発を採用しています。

* Core Engine を中心としたレイヤー構造
* CLI → GUI → 通信の段階開発
* ADRによる設計判断の記録

詳細は `spec/` ディレクトリを参照してください。

---

## ドキュメント

仕様書は `spec/` ディレクトリにあります。

### 主要ドキュメント

* [00_overview.md](spec/00_overview.md) - プロジェクト概要
* [01_architecture.md](spec/01_architecture.md) - アーキテクチャ設計
* [02_core_engine.md](spec/02_core_engine.md) - Core Engine API
* [07_job_schema.md](spec/07_job_schema.md) - Job YAML スキーマ

### MkDocsでドキュメント表示

```bash
pip install mkdocs mkdocs-material
mkdocs serve
# http://127.0.0.1:8000
```

---

## ライセンス

MIT License

---

## 免責事項

本ソフトウェアは研究・開発・テスト用途のみを目的として提供されています。
本ソフトウェアの使用によって発生したいかなる損害についても、作者は責任を負いません。

**生成されるDICOMデータは合成データであり、臨床利用できません。**

---

## 作者

医療ITシステムエンジニアによって開発

---

## 貢献

Issue / Pull Request を歓迎します。

Repository: <https://github.com/jeysun/dicom-test-generator>

---

## 今後の予定

### Phase 0: Core Engine ✅ 完了

* [x] データモデル実装（Pydantic v2）
* [x] UID生成（UUID 2.25 / カスタムルート）
* [x] ピクセルデータ生成（simple\_text / ct\_realistic）
* [x] DICOM構築エンジン（DICOMBuilder / FileMetaBuilder / SpatialCalculator）

### Phase 1: CLI ✅ 完了

* [x] Service Layer（テンプレート読み込み、患者検索、スタディ生成）
* [x] CLIコマンド実装（generate / validate / quick / version）
* [x] Job YAML読み込みと設定マージ
* [x] 進捗表示（tqdm）
* [x] エラーハンドリングと終了コード

### Phase 2: GUI

* [ ] PySide6デスクトップアプリ
* [ ] 非同期処理
* [ ] プログレスバー

### Phase 1.5: Storage SCP（オプション）

* [ ] C-STORE受信
* [ ] PyNetDICOM統合

---

## 関連情報

* DICOM Standard: <https://www.dicomstandard.org/>
* PyDicom: <https://pydicom.github.io/>
* PyNetDICOM: <https://pydicom.github.io/pynetdicom/>

---
