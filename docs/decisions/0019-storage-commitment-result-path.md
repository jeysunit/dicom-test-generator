# ADR-0019: 保管確認の結果は別の Association で受けるのを既定にし、CLI では自動で求めない

- 状態：採用
- 日付：2026-10-19
- 作成日：2026-10-22

## 背景

保管確認（Storage Commitment Push Model）では、モダリティが N-ACTION で問い合わせ、
相手が N-EVENT-REPORT で結果を返す。結果は、同じ Association で返る場合と、
相手が別の Association を張って返す場合がある。主な試験の相手の Orthanc は、
結果を別の Association で非同期に返す（Orthanc Book「DICOM storage
commitment」）。

あわせて、いつ問い合わせるか、画面に何を足すかも決める必要があった。

## 決定

1. **結果はどちらの経路で来ても受け、既定は別の Association（待ち受け）で
   受ける。** N-ACTION の Association はすぐに離す。送り先の
   `commitment_wait_seconds` に秒を入れたときだけ、その秒まで同じ Association で
   待つ。理由：同じ Association で毎回待つと、別の経路で返す相手のときに、
   毎回その秒だけ画面が止まる
2. **Web 画面は、1件が「送信完了」になったらすぐ自動で問い合わせる。CLI は
   `commit --job ID` で問い合わせて待ち、自動では問い合わせない。** 理由：
   CLI の `send` で自動で待つと、`send` が最長 10 分止まる
3. **画面には状態を出すだけにし、問い合わせ直すボタンは足さない。** PACS の
   画面の送信キューに「保管確認」の列を1つ足す。問い合わせ直すのは CLI の
   `commit --job ID`

## 検討した選択肢

- **毎回、同じ Association で決まった秒だけ待つ**：別の経路で返す相手のときに
  毎回待たされる
- **CLI の `send` でも自動で問い合わせて待つ**：`send` が最長 10 分止まる
- **問い合わせ直すボタンを画面に足す**：画面の機能を足すより削る方針
  （spec/12a の 10 章の冒頭）に合わない。CLI で足りる

## 結果

- 保管確認を使うときは、このツールが小さな待ち受け（`modality.listen`。
  N-EVENT-REPORT と C-ECHO だけを受ける）を立てる。相手が Orthanc なら、
  Orthanc の `DicomModalities` にこのツールを登録しておく必要がある
- CLI の `commit` と Web 画面は、同じ待ち受けのポートを同時に使えない

## 出典

- Orthanc Book「DICOM storage commitment」

## 関連

- [spec/12 モダリティエミュレーター](../spec/12_modality_emulator.md) の 8.3
- [spec/12a Web 画面と CLI](../spec/12a_web_screens_and_cli.md) の 10.6・11.8
- [ADR-0021](0021-test-only-commitment-and-mpps-peers.md)
