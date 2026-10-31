# ADR-0027: 緊急の患者の追加撮影は、前の撮影の Study Instance UID と同じ患者を CLI で指定したときだけ受ける

- 状態：採用
- 作成日：2026-10-25
- 最終更新日：2026-11-01

## 背景

PACS の PIR（患者情報の事後照合）の試験で、照合の後もモダリティが仮の患者のまま同じ
Study で撮り続ける場面（IHE PIR の Case 6）を作りたい。DTG は緊急の患者（予約なし）の
追加撮影を断っていた。予約の追加撮影は予約の鍵で前の撮影を引けるが、緊急の撮影には
引くための鍵も、前の撮影の記録も無かった。

## 決定

1. **緊急の撮影も、書き終えたら記録する。** Study Instance UID を鍵に、Study ID と患者の
   値（患者ID・氏名・生年月日・性別）を残す。Study の日時・説明とシリーズの番号は、予約の
   撮影と同じ記録（鍵は `emergency:<Study Instance UID>`）に残す。止まった撮影は記録
   しない（[ADR-0024](0024-exam-once-and-retake.md) と同じ）
2. **追加撮影は、前の撮影の Study Instance UID を指定したときだけ受ける。** 指定した
   患者ID と氏名が記録と違えば断る。別の患者の Study に画像を足さないため。生年月日と
   性別は記録の値を使い、違っても断らない
3. **追加撮影の値は予約の追加撮影にそろえる。** Study Instance UID・Study ID・患者の値は
   前の撮影のまま、受付番号は空のまま、シリーズは新しい Series Instance UID で作る。
   Study の日時・説明は最初の撮影の値、Series Number は続きにする。MPPS は撮影ごとに
   新しい SOP Instance で送る
4. **指定は CLI の `exam --emergency --append --study-uid` だけで行う。** 画面には
   Study Instance UID を指定する欄を作らない。PIR の試験は CLI から実行するので、画面の欄は
   要らない。画面での緊急の患者の追加撮影は、今までどおり断る

## 検討した選択肢

| 案 | 採らなかった理由 |
|----|------------------|
| 同じ患者ID の最後の緊急の撮影に、自動で追加する | 仮の患者ID は使い回されうるので、別の撮影の Study に画像を足すおそれがある |
| Study Instance UID だけを指定させ、患者の値は確かめない | UID の写し間違いで、別の患者の Study に画像を足すおそれがある |
| 画面にも Study Instance UID の欄を足す | 試験は CLI から実行する。欄を足すと画面の型と言葉の決まりの変更が要る |

## 結果

- 照合の後に、同じ Study・同じ仮の患者で撮った画像と MPPS を作れる
- 緊急の撮影も撮影の記録に残るので、状態の保存先の SQLite に行が増える

## 関連

- [spec/12_modality_emulator.md](../spec/12_modality_emulator.md) の 6.3
- [ADR-0024](0024-exam-once-and-retake.md)
