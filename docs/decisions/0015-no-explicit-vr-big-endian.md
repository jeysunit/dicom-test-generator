# ADR-0015: 廃止された Explicit VR Big Endian は生成しない

- 状態：採用
- 日付：2026-10-21
- 作成日：2026-10-22

## 背景

DTG では、Job の Transfer Syntax に Explicit VR Big Endian（1.2.840.10008.1.2.2）
を指定できた。この Transfer Syntax は規格で廃止されている（PS3.5 A.3）。さらに
実装は、画素（OW）を Little Endian のバイト列のまま書き出していた。そのため、
生成したファイルを読み込むと画素値のバイト順が入れ替わっていた（PS3.5 8）。

## 決定

1. **Explicit VR Big Endian のファイルは生成しない。** 受け付ける Transfer Syntax は
   Implicit VR Little Endian と Explicit VR Little Endian の2つにする。理由：廃止
   された形式で、現在の実装は規格どおりに書き出せていない
2. Job で指定されたら、出力フォルダを作成する前に停止する。エラーの種類は次の順で
   決める
   - 装置プロファイルを選択していて、そのプロファイルが Big Endian を持たない：
     `ProfileMismatchError`（CLI の終了コード 2）
   - それ以外の Big Endian の指定：`DICOMValidationError`（終了コード 4）
   - プロファイルの最初の Transfer Syntax が Big Endian で、それを使う経路
     （`quick --profile` とモダリティエミュレーターの撮影）：
     `ProfileMismatchError`（終了コード 2）
3. 異常のデータの経路でも生成しない。異常のデータで生成する違反の定義
   （[ADR-0014](0014-separate-normal-and-abnormal-paths.md)）に含まれないため

## 検討した選択肢

- **画素のバイト順を修正して Big Endian の生成を続ける**：廃止された形式を新しく
  生成する理由が無い。受信側のテストで Big Endian が必要なら、異常のデータの定義に
  追加する変更として別に決める
- **指定を無視して Explicit VR Little Endian で生成する**：指定と異なるファイルが
  できたことに利用者が気付けないので採用しない

## 結果

- 生成するファイルの Transfer Syntax は、読み込んでも値が変わらない2つだけになる
- Big Endian を指定した Job は、生成の前にエラーで停止する

## 出典

- DICOM PS3.5 A.3（Explicit VR Big Endian の廃止）、PS3.5 8（画素のバイト順）

## 関連

- [spec/06 DICOM の規則](../spec/06_dicom_rules.md) の Transfer Syntax
- [ADR-0014](0014-separate-normal-and-abnormal-paths.md)
