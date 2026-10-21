# DICOM Test Data Generator

## 概要

DICOM Test Data Generator（DTG）は、架空の患者の架空の検査の DICOM 画像を作成する
ツールです。作成した画像は、本物の患者のデータを使わずに PACS・RIS・ビューアを
テストするために使います。

主な機能は、DICOM 画像を作成して、フォルダにファイルとして保存することです。
補助の機能として、モダリティのように振る舞うこともできます。RIS からワークリストを
取得して予約の内容で画像を作成し、PACS へ送信します。操作は CLI のほか、Web 画面と
GUI からも行えます。

図の実線は主な機能、点線は補助の機能です。矢印はデータが流れる向きです。

```mermaid
flowchart LR
  DTG["DTG<br/>架空の検査の DICOM 画像を作成"]
  FILES@{ shape: docs, label: "DICOM ファイル（フォルダ）" }
  subgraph TARGET["テスト対象"]
    PACS[("PACS")]
    RIS["RIS"]
  end

  DTG -->|"DICOM 画像"| FILES
  DTG -.->|"DICOM 画像（送信）"| PACS
  RIS -.->|"予約（ワークリスト）"| DTG
```

## 注意

- **医療機器ではありません。** 画像は合成したもので、診断・医療行為・臨床評価・
  AI の学習には使えません
- 本番の PACS には送信せず、テスト用の PACS・RIS にだけ接続してください
- 本ソフトウェアの使用によって生じたいかなる損害についても、作者は責任を負いません

## クイックスタート

Python 3.10 以上で、リポジトリのディレクトリで実行します。

```bash
pip install -r requirements.txt
python -m app.web
python -m app.cli quick -p P000001 -m ct_generic -s 1 -i 3 -o output/
```

2行目で Web 画面を起動し、<http://127.0.0.1:8080/> を開きます。3行目は、架空の
患者の CT 画像を3枚 `output/` に生成します。

## ドキュメント

使い方・仕様・設計の判断は [docs/README.md](docs/README.md) から辿れます。

## ライセンス

MIT License
