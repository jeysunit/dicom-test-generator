# Design

## Context

### 今の DTG

- 同じ予約で何度でも「撮影」できる。2回目以降は同じ Study Instance UID で新しい
  シリーズを作る（spec 12 の 6.3）。MPPS を使うときは、撮影ごとに新しい MPPS の
  SOP Instance を作る
- 2回目以降の Study Date・Study Time は撮影の時刻で作り直し、Series Number は 1 から
  振り直す
- 予約に Study Instance UID が無いときに DTG が作った UID は、予約の鍵ごとに SQLite に
  記録し、2回目も使う（`generated_study_uids`）

### 規格と IHE が定めていること（事実）

1. **終わった MPPS は更新しない。** SCU は、COMPLETED か DISCONTINUED を N-SET した
   MPPS の SOP Instance を変更してはならず、その MPPS の一部として新しい Composite
   SOP Instance を作ってはならない。続けて作るときは新しい MPPS を作ってよい
   （PS3.4 F.7.2.2.2 と Note）。SCP は、IN PROGRESS 以外の MPPS への N-SET を
   `0110H` で断る（PS3.4 F.7.2.2.3）
2. **終わった手順にシリーズを足さない。** 1つのシリーズは複数の PPS の出力を
   持てないので、手順を終えた後に画像を足すときは新しいシリーズを作る（IHE RAD TF-2
   4.8.4.1.1.1）
3. **Append Case。** 予約で1つ目の PPS を作った後、予約に無い PPS を続けて足す形を
   IHE は Append Case と呼ぶ。例は「画質が悪い画像の撮り直し（redo）」と「追加の
   部位の撮影（add）」。足した PPS はすべて同じ Requested Procedure と元の SPS を
   指し、予約の値を MPPS と画像の Request Attributes Sequence に写す（IHE RAD TF-2
   4.6.4.1.2.3.3）
4. **Append Case の値。** 追加の画像と MPPS の Study Instance UID・受付番号・予約の値は
   元と同じ（MWL から写す）。PPS ID・PPS の開始日時は新しく作る。追加の画像の
   Study Date・Study Time・Study Description は元の画像の値を使い回す（IHE RAD
   TF-2x Table A.1-3 と IHE-A.3.3）
5. **別の検査にする場合。** IHE は、追加の撮影を RIS で予約し直せば「2つの Simple
   Case になる」と書いている（IHE RAD TF-2 4.6.4.1.2.3.3 の Note）。予約し直せば
   新しい Requested Procedure になり、Study Instance UID も RIS が新しく出す
6. **モダリティが Study Instance UID を作れる場合は限られる。** 予約の無い撮影
   （Unscheduled Case）と、別々の Requested Procedure の SPS を1つの PPS で行う
   場合だけで、それ以外は RIS が出した UID を使う（IHE RAD TF-2 4.8.4.1.1.1）

承認者の考え「再撮影すると、現実の運用では別スタディ扱いでは」について：規格と
IHE が定めているのは、上の 3〜6 の2つの道である。同じ予約のまま撮り直す・足す
なら Append Case（同じ Study）、RIS で予約し直すなら新しい Study になる。どちらを
使うかは施設の運用で決まり、規格と IHE はどちらかを求めていない。ただし、同じ
予約のままモダリティが新しい Study Instance UID を作ることは、6 により認められて
いない。

## Goals / Non-Goals

**Goals:**

- 予約での撮影を1回で撮影済みにし、2回目は「追加撮影」として Append Case の値で作る
- 別の検査としての撮り直しは、RIS の新しい予約で行えることを明記する

**Non-Goals:**

- 緊急の患者（予約なし）の撮影の変更。今のまま何度でも撮れる（毎回別の Study）
- Group Case（複数の SPS を1つの PPS で行う）
- RIS に予約の状態を返すこと（MPPS 以外の方法）

## Decisions

1. **推奨：追加撮影を Append Case で作り、別の Study にする撮り直しは RIS の新しい
   予約に任せる。** 理由：DTG は RIS・PACS のテストに使うので、IHE が定める2つの
   道の両方を作れるとよい。同じ予約の撮り直しを DTG が別の Study にすると、上の
   事実 6 に反する画像を、異常のデータの指定なしに作ることになる。RIS の新しい予約
   なら、今の機能のまま新しい Study を作れる。
   採用しなかった案：同じ予約の2回目を、DTG が新しい Study Instance UID で作る
   （事実 6 に反する）。2回目を断るだけにする（Append Case を試せない）
2. **撮影済みの記録。** 予約の鍵ごとに、最初の撮影の Study Instance UID・Study
   Date・Study Time・Study Description と、作ったシリーズの数を SQLite に記録する。
   今の `generated_study_uids` を、この記録に広げる（既存の行は UID だけの記録として
   移す）。撮影済みにするのは画像を書き出し終えた後で、撮影が止まったら記録しない
3. **MPPS を使わない設定でも撮影済みにする。** 撮影済みは DTG の中の決まりで、MPPS を
   送ったかとは別に扱う。MPPS の送信に失敗しても撮影済みにする（MPPS の再送は
   `mpps retry`）
4. **Series Number は続きの番号にする。** 同じ Study に同じ番号のシリーズが並ぶと、
   PACS の画面で区別しにくい。前に作ったシリーズの数の続きから振る（この仕様の
   決定。IHE の Table A.1-3 は Series Number を定めていない）
5. **Study Description。** 今は予約の Requested Procedure Description を使っている。
   追加撮影でも最初の撮影の値をそのまま使う（IHE-A.3.3）
6. **画面。** 撮影済みの予約を開いたら、「撮影」「撮影して送る」を押せなくし、
   「追加撮影」（プライマリ）を出す。追加撮影の結果にも、今と同じく MPPS の状態を
   出す。一覧の印は今の「別の装置」と同じ形で「撮影済み」を出す

## Risks / Trade-offs

- [ワークリストの予約の鍵は Study Instance UID・Requested Procedure ID・SPS ID・
  受付番号から作るので、RIS が予約の値を変えると別の鍵になり、撮影済みが外れる] →
  鍵が変わったら別の予約として扱う（RIS が予約を変えたことになるため）。spec に書く
- [撮影済みにした後に、利用者が同じ予約を最初から撮り直したい] → RIS で予約し
  直す。DTG の記録を消すコマンドは作らない（状態の保存先を消せば戻る）

## Open Questions

- 追加撮影を「撮影済み」の予約だけに出すか、撮影済みでない予約にも出すか。今回は
  撮影済みの予約だけに出す（Append Case は最初の PPS の後にだけある）
