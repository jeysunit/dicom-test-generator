# ADR-0015: 廃止の Explicit VR Big Endian は作らない

- 状態：採用
- 日付：2026-10-21
- 作成日：2026-10-22

## 背景

このツールは、Job で Transfer Syntax に Explicit VR Big Endian
（1.2.840.10008.1.2.2）を選べた。この Transfer Syntax は規格で廃止されている
（PS3.5 A.3）。さらに実装は、画素（OW）を Little Endian のバイト列のまま
書いていた。そのため、作ったファイルを読み戻すと画素の値が入れ替わった
（PS3.5 8）。

## 決定

1. **Explicit VR Big Endian のファイルは作らない。** 受ける Transfer Syntax は
   Implicit VR Little Endian と Explicit VR Little Endian の2つにする。
   理由：廃止の形で、いまの実装は規格どおりに書けていない
2. **Job で指定されたら、出力のフォルダを作る前に止める。** 誤りの種類は
   次の順で決める
   - 装置のプロファイルを選んでいて、プロファイルが Big Endian を持たない：
     `ProfileMismatchError`（CLI の終了コード 2）
   - それ以外の Big Endian の指定：`DICOMValidationError`（終了コード 4）
   - プロファイルの最初の Transfer Syntax が Big Endian で、その形を使う経路
     （`quick --profile` とモダリティエミュレーターの撮影）：
     `ProfileMismatchError`（終了コード 2）
3. **異常のデータの経路でも作らない。** 異常のデータの約束
   （[ADR-0014](0014-separate-normal-and-abnormal-paths.md)）に無い違反だから

## 検討した選択肢

- **画素のバイト順を直して Big Endian を作り続ける**：廃止の形を新しく作る
  理由が無い。受け取る側の試験で Big Endian が要るなら、異常のデータの約束に
  足す変更として別に決める
- **黙って Explicit VR Little Endian に替えて作る**：指定と違うファイルが
  できたことに利用者が気づけないので採らない

## 結果

- 作るファイルの Transfer Syntax は、読み戻しで値が変わらない2つだけになる
- Big Endian を指定していた Job は、生成の前に誤りで止まる

## 出典

- DICOM PS3.5 A.3（Explicit VR Big Endian の廃止）、PS3.5 8（画素のバイト順）

## 関連

- [spec/06 DICOM の規則](../spec/06_dicom_rules.md) の Transfer Syntax
- [ADR-0014](0014-separate-normal-and-abnormal-paths.md)
