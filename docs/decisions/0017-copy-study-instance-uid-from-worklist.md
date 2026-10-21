# ADR-0017: Study Instance UID は予約から写し、予約に無いときだけ作る

- 状態：採用
- 日付：2026-10-18
- 作成日：2026-10-22

## 背景

モダリティエミュレーターは、ワークリストの予約の値を画像に写す。
Study Instance UID を予約から写すか、このツールが作るかを決める必要があった。
PACS と RIS の連携では、予約と届いた検査を Study Instance UID で結びつける
ことが多く、ここがずれると連携の試験にならない。

## 決定

1. **予約に Study Instance UID があれば、その値を画像に写す。** 理由：IHE は、
   Study Instance UID を Order Filler が作ってワークリストで渡すことを基本とし、
   モダリティが作るのは予約なしの形などに限っている（RAD TF-2 4.8.4.1.1.1）。
   Orthanc の Worklists のプラグインの「検査が届いたら予約を消す」
   （`DeleteWorklistsOnStableStudy`）も、予約の UID と届いた検査の UID の
   一致で動く
2. **予約に無いときは、このツールが作る（2.25 の形）。** 撮影の画面と CLI に、
   作ったことを知らせる
3. **同じ予約で2回撮ったら、同じ Study に新しいシリーズを足す。** このツールが
   作った UID は予約の鍵ごとに状態の置き場の SQLite に覚え、2回目も同じ UID を
   使う（RAD TF-2 4.8.4.1.1.1 の「終わった手順にシリーズを足さない」に従い、
   Series は新しく作る）
4. **予約なし（緊急の患者）では、いつも作る**（RAD TF-2x Table A.1-2）

## 検討した選択肢

- **いつもこのツールが作る**：予約と画像の Study Instance UID が合わなくなり、
  PACS・RIS の突き合わせの試験ができない。採らない

## 結果

- 予約の UID が入った画像を送れるので、予約と検査の突き合わせを試せる
- 予約の UID はワークリストの相手が自由に入れられる値なので、写す前に UID の
  形を確かめる（spec/12 の 6.5）

## 出典

- IHE Radiology TF-2 4.8.4.1.1.1、TF-2x Appendix A（Table A.1-1・A.1-2）
- Orthanc Book「Worklists plugin」

## 関連

- [spec/12 モダリティエミュレーター](../spec/12_modality_emulator.md) の 6.2・6.3
