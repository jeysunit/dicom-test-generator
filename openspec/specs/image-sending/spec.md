# image-sending Specification

## Purpose

撮影した画像を PACS へ送る操作（C-STORE。PS3.4 Annex B）と、送信キュー・再送・
その表示を定める。

## Requirements

### Requirement: 送信キューの表に画像の受付番号を示す

送信キューの件は、送るフォルダの画像の Accession Number (0008,0050) を受付番号
として持ち、PACS の画面の送信キューの表に表示しなければならない（SHALL）。画面から
の送信と CLI の `send` の両方に効く。画像の受付番号が空なら「—」を表示する。

#### Scenario: 予約で撮って送る

- **WHEN** 受付番号 `A0001` の予約で「撮影して送る」を押す
- **THEN** PACS の画面の送信キューの表の、その件の受付番号の欄に `A0001` が表示される

#### Scenario: CLI で送る

- **WHEN** 受付番号 `A0002` の画像のフォルダを `python -m app.cli send <フォルダ>` で送る
- **THEN** `queue list` の出力と PACS の画面の、その件の受付番号が `A0002` になる

#### Scenario: 緊急の患者

- **WHEN** 緊急の患者（受付番号は空）で撮影して送る
- **THEN** その件の受付番号の欄に「—」が表示される

#### Scenario: この変更の前に作った件

- **WHEN** 受付番号が空のまま記録された件があり、そのフォルダの画像の受付番号が `A0003` である
- **THEN** PACS の画面の受付番号の欄に `A0003` が表示される
