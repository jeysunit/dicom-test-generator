# ADR-0019: 保管確認の結果は別の Association で受けることを既定にし、CLI では自動で要求しない

- 状態：採用
- 作成日：2026-10-22
- 最終更新日：2026-10-22

## 背景

保管確認（Storage Commitment Push Model）では、モダリティが N-ACTION で要求し、
相手が N-EVENT-REPORT で結果を返す。結果は、同じ Association で返る場合と、相手が
別の Association を確立して返す場合がある。主なテスト相手の Orthanc は、結果を別の
Association で非同期に返す（Orthanc Book「DICOM storage commitment」）。

あわせて、いつ要求するか、画面に何を追加するかも決める必要があった。

## 決定

1. **結果はどちらの経路で来ても受け、既定は別の Association（待ち受け）で受ける。**
   N-ACTION の Association はすぐに解放する。送信先の `commitment_wait_seconds` に
   秒数を設定したときだけ、その秒数まで同じ Association で待つ。理由：同じ
   Association で毎回待つと、別の経路で返す相手のときに、毎回その秒数だけ画面が
   止まる
2. Web 画面は、1件が送信完了になったらすぐ自動で要求する。CLI は `commit --job ID`
   で要求して待ち、自動では要求しない。理由：CLI の `send` で自動で待つと、`send`
   が最長 10 分止まる
3. 画面には状態を表示するだけにし、再要求のボタンは追加しない。PACS の画面の
   送信キューに「保管の確認」の列を1つ追加する。再要求は CLI の `commit --job ID`
   で行う

## 検討した選択肢

- **毎回、同じ Association で決まった秒数だけ待つ**：別の経路で返す相手のときに
  毎回待たされる
- **CLI の `send` でも自動で要求して待つ**：`send` が最長 10 分止まる
- **再要求のボタンを画面に追加する**：画面の機能は追加するより減らすという方針
  （spec/12a の 10 章の冒頭）に合わない。CLI で足りる

## 結果

- 保管確認を使うときは、DTG が小さな待ち受け（`modality.listen`。N-EVENT-REPORT と
  C-ECHO だけを受ける）を起動する。相手が Orthanc なら、Orthanc の
  `DicomModalities` に DTG を登録しておく必要がある
- CLI の `commit` と Web 画面は、同じ待ち受けのポートを同時に使えない

## 出典

- Orthanc Book「DICOM storage commitment」

## 関連

- [spec/12 モダリティエミュレーター](../spec/12_modality_emulator.md) の 8.3
- [spec/12a Web 画面と CLI](../spec/12a_web_screens_and_cli.md) の 10.6・11.8
- [ADR-0021](0021-test-only-commitment-and-mpps-peers.md)
