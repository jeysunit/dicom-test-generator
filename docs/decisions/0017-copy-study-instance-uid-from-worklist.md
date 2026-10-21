# ADR-0017: Study Instance UID は予約から転記し、予約に無いときだけ生成する

- 状態：採用
- 日付：2026-10-18
- 作成日：2026-10-22

## 背景

モダリティエミュレーターは、ワークリストの予約の値を画像に転記する。Study Instance
UID を予約から転記するか、DTG が生成するかを決める必要があった。PACS と RIS の
連携では、予約と受信した検査を Study Instance UID で照合することが多く、ここが
ずれると連携のテストにならない。

## 決定

1. **予約に Study Instance UID があれば、その値を画像に転記する。** 理由：IHE は、
   Study Instance UID を Order Filler が生成してワークリストで渡すことを基本とし、
   モダリティが生成するのは予約の無い場合などに限っている（RAD TF-2 4.8.4.1.1.1）。
   Orthanc の Worklists プラグインの「検査を受信したら予約を削除する」機能
   （`DeleteWorklistsOnStableStudy`）も、予約の UID と受信した検査の UID の一致で
   動作する
2. 予約に無いときは、DTG が生成する（2.25 の形式）。生成したことを撮影の画面と
   CLI に表示する
3. 同じ予約で2回撮影したら、同じ Study に新しいシリーズを追加する。DTG が生成した
   UID は予約のキーごとに状態の保存先の SQLite に記録し、2回目も同じ UID を使う
   （RAD TF-2 4.8.4.1.1.1 の「完了した手順にシリーズを追加しない」に従い、
   Series は新しく生成する）
4. 予約の無い撮影（緊急の患者）では、常に生成する（RAD TF-2x Table A.1-2）

## 検討した選択肢

- **常に DTG が生成する**：予約と画像の Study Instance UID が一致しなくなり、
  PACS・RIS の照合のテストができない。採用しない

## 結果

- 予約の UID を持つ画像を送信できるので、予約と検査の照合をテストできる
- 予約の UID はワークリストの取得先が自由に設定できる値なので、転記する前に UID の
  形式を検証する（spec/12 の 6.5）

## 出典

- IHE Radiology TF-2 4.8.4.1.1.1、TF-2x Appendix A（Table A.1-1・A.1-2）
- Orthanc Book「Worklists plugin」

## 関連

- [spec/12 モダリティエミュレーター](../spec/12_modality_emulator.md) の 6.2・6.3
