# Proposal

## Why

今の DTG は、同じ予約（Scheduled Procedure Step）から何度でも「撮影」でき、2回目
以降は同じ Study に新しいシリーズを足す（spec 12 の 6.3）。実機のモダリティでは、
予約で撮影を終えたら（MPPS を COMPLETED にしたら）その予約は終わり、同じ予約で
もう一度撮るのは「追加撮影」として別に扱う。テストの道具としても、1回目の撮影と
追加の撮影を区別して作れるほうが、RIS・PACS の扱いを確かめやすい。

あわせて、今の2回目の撮影は Study Date・Study Time を撮影の時刻で作り直している。
IHE の Append Case では、追加の画像の Study Date・Study Time・Study Description は
元の画像の値を使い回す（IHE RAD TF-2x Appendix A の IHE-A.3.3）ので、これに
合わせる。

## What Changes

- 予約で撮影を終えたら、その予約を「撮影済み」として状態の保存先に記録する。
  撮影済みの予約では「撮影」「撮影して送る」を押せなくし、サーバーも断る
- 撮影済みの予約には「追加撮影」のボタンを出す。追加撮影は IHE の Append Case
  （IHE RAD TF-2 4.6.4.1.2.3.3、RAD TF-2x Table A.1-3）に従い、同じ Study Instance
  UID・受付番号・元の予約の値で、新しいシリーズと新しい MPPS を作る
- 追加撮影の画像の Study Date・Study Time・Study Description は、その予約の最初の
  撮影の値にする。Series Number は前の撮影の続きの番号にする
- ワークリストの一覧で、撮影済みの予約に「撮影済み」の印を付ける
- 撮影が止まった（MPPS を DISCONTINUED にした）ときは撮影済みにせず、同じ予約から
  もう一度「撮影」できる
- 別の検査として撮り直すときは、RIS で新しい予約を作ってワークリストから選ぶ。
  DTG は、予約に Study Instance UID がある予約で、新しい Study Instance UID を
  作らない（IHE RAD TF-2 4.8.4.1.1.1）
- CLI の `exam --from-worklist` も同じ決まりにし、追加撮影は `--append` で行う

## Capabilities

### New Capabilities

- `exam-workflow`: 予約での撮影・追加撮影・緊急の撮影の関係と、MPPS・Study の
  値の決まり

### Modified Capabilities

（なし）

## Impact

- サービス：`app/modality/service.py`（撮影済みの判定・追加撮影の依頼・Study の値の
  使い回し・Series Number の続き）、`app/modality/queue.py`（予約ごとの撮影の記録。
  今の `generated_study_uids` を広げる）
- 画像の作成：`StudyConfig` に渡す Study Date・Time・Description と、シリーズの
  開始番号
- 画面：撮影の画面のボタン（`exam.html`・`_exam_actions.html`）、ワークリストの
  一覧の印（`app/web/display.py` の `item_marks`）
- CLI：`exam --append`
- spec：12 の 6.2・6.3・8.4、12a の 10.4・10.5・10.8・11.4
- ADR：撮影済みの扱いと追加撮影の決定（Append Case を選び、撮り直しを DTG で新しい
  Study にしない理由）
- 利用者：同じ予約で「撮影」を2回押す使い方はできなくなり、「追加撮影」を使う
