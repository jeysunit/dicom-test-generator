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

### ✅ モダリティのダミー（Phase 3a・3b・3c）

* ワークリストを取得し、予約の値で画像を作り、PACS へ送る（ウェブの画面と
  CLI。[spec/12_modality_emulator.md](spec/12_modality_emulator.md)）。
  起動のしかたは下の「モダリティのダミーのウェブの画面」
* 保管の確認（Storage Commitment）と MPPS は、設定で選んだときだけ使う
  （下の「保管の確認と MPPS（Phase 3c）」）

### ✅ テンプレートベース設計

* モダリティテンプレート
* 病院設定テンプレート
* 装置のプロファイル：装置のコンフォーマンスステートメントを読んで写し、
  その装置の DICOM の出し方を擬態する。実在の装置のプロファイルは
  リポジトリの外に置く（[spec/13_device_profiles.md](spec/13_device_profiles.md)）
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
python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o output/

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

modality_template: "ct_generic"
pixel_spec:
  mode: "simple_text"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: ""       # 日本語名の場合: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: false            # 日本語名の場合: true
  use_phonetic: false               # 日本語名の場合: true
```

---

## GUI（Phase 2）

デスクトップGUI実装予定。

---

## Storage SCP（Phase 1.5）

DICOM通信による受信機能を追加予定。

---

## モダリティのダミーのウェブの画面（Phase 3b）

ワークリスト・撮影・PACS・設定の4つの画面で「取得→選ぶ→撮る→送る→確かめる」を
流します（[spec/12_modality_emulator.md](spec/12_modality_emulator.md) の 10 章）。
試験用の PACS・RIS にだけつないでください。

### 起動

```bash
# 設定は config/app_config.yaml の modality: と web: の節
python -m app.web
python -m app.web --config config/app_config.yaml
```

ブラウザで <http://127.0.0.1:8080/> を開きます。既定は手元（127.0.0.1）だけで
待ち受け、認証はありません。Node も Tailwind CSS の実行ファイルも要りません
（作った CSS と htmx を `app/web/static/` に置いてあります）。

### 網に出すとき

`web.bind_address` を手元の外（`0.0.0.0` など）にするときは HTTP Basic が必須です。
パスワードを1行だけ書いたファイルを作り、環境の変数で指します。ファイルが無い・空なら
起動しません（終了コード 2）。利用者の名前は `dtg` です。

```bash
DTG_WEB_PASSWORD_FILE=/path/to/password.txt python -m app.web
```

* パスワードは設定のファイルに書きません
* この画面は HTTPS を持ちません。網に出すときは、前段の逆プロキシで TLS を付けてください
  （`Host` の見出しをそのまま渡す設定にします）
* 書き込みの要求は、同じ origin と CSRF の token のときだけ受けます

### 画面の静的な物の出どころ

| 物 | 版 | 取得の元 | sha256 |
|----|----|----------|--------|
| htmx（`app/web/static/htmx.min.js`） | v2.0.9 | GitHub の bigskysoftware/htmx の releases | `57d9191515339922bd1356d7b2d80b1ee3b29f1b3a2c65a078bb8b2e8fd9ae5f` |
| Lucide のアイコン（`app/web/static/icons/`。ISC License、同じ所に `LICENSE`） | 1.48.0 | GitHub の lucide-icons/lucide の releases（`lucide-icons-1.48.0.zip`） | `e27a6b58bebc563581f89668a5a652782075a85a07568e4fd8051a17ce81dba6`（zip） |
| Tailwind CSS の standalone の実行ファイル（CSS を作るときだけ） | v4.3.3 | GitHub の tailwindlabs/tailwindcss の releases | `scripts/build_css.sh` に OS ごとに固定 |

取り直す・作り直すときは次を流します。どちらも sha256 が合わなければ止まります。

```bash
bash scripts/fetch_web_assets.sh   # htmx と Lucide のアイコン
bash scripts/build_css.sh          # app/web/styles/input.css から app/web/static/app.css
```

CI は CSS を作り直し、commit した `app.css` と差が無いことを確かめます。

---

## 保管の確認と MPPS（Phase 3c）

どちらも既定は使いません。`config/app_config.yaml` の `modality:` の節で選びます
（[spec/12_modality_emulator.md](spec/12_modality_emulator.md) の 8.3・8.4・12 章）。

### 保管の確認（Storage Commitment）

```yaml
modality:
  listen:                       # 結果（N-EVENT-REPORT）を受ける待ち受け
    bind_address: "127.0.0.1"
    port: 11113
  destinations:
    - name: "PACS_TEST"
      ae_title: "PACS_TEST"
      host: "127.0.0.1"
      port: 4242
      storage_commitment: true
      commitment_timeout_seconds: 600   # 結果を待つ秒
      commitment_wait_seconds: 0        # 同じ Association で待つ秒（0 は待たない）
```

* 画面（`python -m app.web`）は待ち受けを立て、送り先へ「送れた」になった件の保管の
  確認をすぐに求めます。PACS の画面の待ち行列の「保管の確認」の列に、確認待ち・確認済・
  確認の失敗・確認の時間切れが出ます
* CLI では自動で求めません。送った後に `commit` で求め、結果を待ちます。確認済なら
  終了コード 0、そうでなければ 5 です。画面が同じ待ち受けのポートで動いているときは
  待ち受けを立てられないので、終了コード 2 で止まります

```bash
python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO" --send
python -m app.cli queue list               # 件の ID と COMMIT の列
python -m app.cli commit --job 1 --wait 60
```

* 結果は、相手が別の Association で返すのを既定にしています。同じ Association でしか
  返さない相手のときだけ、`commitment_wait_seconds` に秒を入れます

### 試験用の Orthanc で確かめる手順

Orthanc（1.6.0 から）は保管の確認を受け、結果を別の Association で返します。結果を返す
先として、この道具を Orthanc の設定の `DicomModalities` に登録します。

1. Orthanc の設定に、この道具の AE タイトル・住所・待ち受けのポートを足します
   （例：`"DicomModalities": { "dtg": [ "DTG_CT01", "127.0.0.1", 11113 ] }`）。
   Orthanc をコンテナで動かすときは、コンテナから届く住所を書き、この道具の
   `listen.bind_address` もその住所で受けるようにします（既定の 127.0.0.1 では
   コンテナから届きません）
2. この道具の送り先を Orthanc の AE タイトル・住所・DICOM のポートにし、
   `storage_commitment: true` にします
3. `python -m app.web` を起動し、撮影の画面で [撮影して送る] を押します
4. PACS の画面の待ち行列で、その件の「保管の確認」が「確認済」になることを確かめます。
   CLI なら、画面を止めてから `python -m app.cli commit --job <ID>` で「confirmed」と
   終了コード 0 を確かめます

### MPPS

```yaml
modality:
  worklist:
    use_mpps: true              # MPPS を送る
  mpps:                         # 書かなければワークリストの相手へ送る
    ae_title: "MPPS_TEST"
    host: "127.0.0.1"
    port: 4243
    timeout_seconds: 30
```

* 撮影を始めるときに N-CREATE（IN PROGRESS）、作り終わりに N-SET（COMPLETED）を送ります。
  作る途中で止まったら N-SET（DISCONTINUED）を送ります
* 送れなくても撮影と送信は止めません。撮影の画面と CLI（`[WARN] MPPS ...`）に出し、
  知らせを待ち行列に残します。`retry.max_attempts` の回数だけすぐに送り直し、残りは
  `mpps retry` で送ります
* `exam --mpps`・`--no-mpps` で、その撮影だけ設定を上書きできます。装置のプロファイルが
  `services.mpps: false` なら送りません
* Orthanc は MPPS を受けません。MPPS を受ける試験の相手（RIS など）を使ってください

```bash
python -m app.cli mpps list
python -m app.cli mpps retry
```

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
├── profiles/examples/  # 架空の装置のプロファイルの例（実在の装置は外に置く）
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
