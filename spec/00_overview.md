# 00. プロジェクト概要

**DICOM Test Data Generator**（DICOMテストデータ生成ツール、リポジトリ名
`dicom-test-generator`）は、検査装置（モダリティ）のふりをして、架空の患者の
DICOM 画像を作り、画像サーバー（PACS）へ送る試験用のツールである。
RIS や PACS、ビューア、画像の取り込みシステムを、本物の患者のデータを使わずに
試すために使う。

**作るピクセルデータは合成データであり、実際の医療画像ではない。臨床には使えない。**

---

## 目的

1. 画像を受ける側のシステムの試験に使う、多様なメタデータを持つ DICOM
   ファイルを作る（正常なデータと、安全性のレベル別の異常なデータ）
2. 検査装置のふるまい（ワークリストの取得、予約に沿った撮影、画像の送信、
   保管の確認、MPPS）を擬態し、受ける側を手元で試せるようにする

このツールの目的は、プログラムを書くことではなく、試験の相手になることである。

---

## 非対象

- 実際の医療画像の生成（診断目的）
- PACS 本番環境への直接投入
- 画像を受信して保存すること。受信は PACS の役目で、モダリティの擬態という
  目的の外にある。試験の相手は、使う側が自分で用意する
  （[ADR-0013](../adr/0013-remove-storage-scp.md)）
- 患者のプライバシーデータの管理
- 医療機器としての認証の取得
- 他モダリティ（MR・CR・DX・US など）と Query/Retrieve。未実装

---

## 主要機能

| 機能 | 内容 | 仕様 |
|------|------|------|
| DICOM ファイルの生成 | 病院・モダリティ別のテンプレート、患者マスターの情報、1 スタディに複数のシリーズと画像、日本語とローマ字の切り替え、CT のリアルモードのピクセル | [02](02_core_engine.md)・[06](06_dicom_rules.md)・[07](07_job_schema.md) |
| 異常データの生成 | 安全性のレベル（none・mild・moderate・severe）別 | [02](02_core_engine.md)・[06](06_dicom_rules.md) |
| モダリティのダミー | ワークリスト（MWL、検査の予約の一覧）の取得、予約からの撮影、C-STORE での送信、失敗した送信の再送、保管の確認（Storage Commitment）、MPPS | [12](12_modality_emulator.md) |
| 装置のプロファイル | ある装置の DICOM の出し方（製造元・機種・属性・プライベート領域）をテンプレートに重ねる | [13](13_device_profiles.md) |
| CLI | 生成・検証・簡易生成と、モダリティのダミーの操作 | [04](04_cli.md)・[12a](12a_web_screens_and_cli.md) |
| ウェブの画面 | ワークリスト・撮影・PACS・設定の画面（FastAPI + Jinja2 + HTMX） | [12a](12a_web_screens_and_cli.md) |
| デスクトップの画面（凍結） | PySide6 の基本の生成フローだけ。これ以上は広げない | [05](05_gui.md)・[ADR-0011](../adr/0011-modality-emulator.md) |

段（Phase）ごとの完了と未了は、リポジトリ直下の `WORKFLOW.md` の表が唯一の
記録である。この文書には書かない。

---

## 技術スタック

依存の正本は `requirements.txt` である。

| カテゴリ | 技術 | 用途 |
|----------|------|------|
| 言語 | Python 3.10 以上 | CI は 3.10 と 3.12 で流す |
| DICOM の読み書き | pydicom | データセットの構築・保存 |
| DICOM の通信 | pynetdicom | MWL・C-STORE・C-ECHO・Storage Commitment・MPPS（SCU 側） |
| 設定 | PyYAML | テンプレート・Job・装置のプロファイル・設定 |
| データモデル | Pydantic v2 | モデルと検証 |
| 画像 | Pillow・NumPy | ピクセルデータの生成 |
| CLI | argparse・tqdm | コマンドラインと進捗表示 |
| ウェブの画面 | FastAPI・uvicorn・Jinja2・HTMX・Tailwind CSS | サーバー描画の画面。CSS と HTMX は固定した版を `scripts/` で用意する |
| デスクトップの画面（凍結） | PySide6 | 基本の生成フローだけ |
| 試験 | pytest・pytest-qt・httpx | `tests/` |

---

## 対象ユーザー

- 医療システムの開発者：DICOM の取り込み機能や、ワークリストの連携のデバッグ
- QA エンジニア：異常なデータを含む試験ケースの作成
- 医療 IT の開発者：製品の検証用ダミーデータの生成

---

## 開発方針

- **仕様を先に固めてから実装する。** 仕様は `spec/`、決めた理由は `adr/` に置く
- **機能は足すより削る。** 過剰設計を避け、最短で実装できる構造にする
- **層を分ける。** UI は Service を通して Core を使う。依存は上から下の一方向
  （[01_architecture.md](01_architecture.md)）
- **医療の仕様は変えない。** DICOM の決まりは動かさない
- **Core は単体で試験できる。** 通信・ファイル・ログを持たない処理は Core に置く
- 生成 AI による実装を前提に、インターフェースを明確に書く

---

## ライセンス

MIT License（オープンソース化を想定）

---

## リポジトリ構成

```text
dicom-test-generator/
├── spec/        # 仕様書
├── adr/         # Architecture Decision Records
├── app/         # アプリケーションコード（役割は 01_architecture.md）
├── templates/   # モダリティ・病院のテンプレート
├── profiles/    # 装置のプロファイル（公開してよい例）
├── config/      # 設定ファイル（app_config.yaml）
├── data/        # 患者マスター（架空の患者）
├── examples/    # Job YAML の例
├── scripts/     # 画面の静的ファイルを用意するスクリプト
├── tests/       # 試験
├── README.md
└── WORKFLOW.md  # 開発の流れと段（Phase）の状態
```

---

## 読む順

1. [01_architecture.md](01_architecture.md)：層とディレクトリの役割
2. [02_core_engine.md](02_core_engine.md)・
   [03_data_models.md](03_data_models.md)：Core とモデル
3. [12_modality_emulator.md](12_modality_emulator.md)：モダリティのダミーの仕様
