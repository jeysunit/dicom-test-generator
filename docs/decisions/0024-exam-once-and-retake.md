# ADR-0024: 予約での撮影は1回で撮影済みにし、撮り直しの形は設定で選ぶ

- 状態：採用
- 作成日：2026-10-23
- 最終更新日：2026-10-23

## 背景

DTG は同じ予約（Scheduled Procedure Step）から何度でも撮影でき、2回目以降は同じ
Study に新しいシリーズを足していた。2回目の Study Date・Study Time は撮影の時刻で
作り直していた。実機のモダリティでは、予約で撮影を終えたら、その予約は終わる。
同じ予約でもう一度撮るのは別の操作として扱う。

規格と IHE が定めていることは次のとおり。

- COMPLETED か DISCONTINUED にした MPPS は変更できず、その MPPS の一部として画像を
  作ることもできない。続けて作るときは新しい MPPS を作ってよい（PS3.4 F.7.2.2.2）
- 手順を終えた後に画像を足すときは、新しいシリーズを作る。モダリティが Study
  Instance UID を作ってよいのは、予約の無い撮影などの例外に限る（IHE RAD TF-2
  4.8.4.1.1.1）
- 同じ予約のまま撮り直す（redo）・足す（add）形を、IHE は Append Case と呼ぶ。足した
  PPS は同じ Requested Procedure と元の SPS を指す（RAD TF-2 4.6.4.1.2.3.3）。追加の
  画像の Study Instance UID・受付番号は元と同じで、Study Date・Study Time・Study
  Description は元の画像の値を使い回す（RAD TF-2x Table A.1-3 と IHE-A.3.3）
- 追加の撮影を RIS で予約し直せば、2つの Simple Case になる（同じ節の Note）

一方、撮り直しを別の検査として扱い、受付番号から Study Instance UID まで変える施設も
ある。どちらを使うかは施設の運用で決まり、規格と IHE はどちらかを求めていない。

## 決定

1. **予約での撮影は1回で撮影済みにする。** 画像を書き出し終えたら記録し、撮影が
   止まった予約は記録しない。撮影済みの予約での通常の撮影は断る
2. **撮り直しの形は設定 `modality.retake_mode` で選ぶ。** `append` は Append Case で
   「追加撮影」を行い、`new_order` は RIS の新しい予約で撮り直す
3. **既定は `append` にする。** 理由：規格と IHE が定める形で、RIS が撮り直しの予約を
   作れなくても使えるため。`new_order` は、RIS の側に撮り直しの予約を作る機能がある
   環境で選ぶ
4. **どちらの形でも、DTG は同じ予約で新しい Study Instance UID や受付番号を作らない。**
   理由：同じ予約でモダリティが Study Instance UID を作ることは IHE RAD TF-2
   4.8.4.1.1.1 が認めておらず、受付番号は RIS が発番する値だから。異常のデータの
   指定なしに、規格や IHE に反する画像を作らない（ADR-0014）
5. **追加撮影は1回ごとに新しい MPPS と新しい PPS ID を作り、PPS の開始はその撮影の
   日時にする。** Series Number は前に作ったシリーズの続きから振る（同じ Study に同じ
   番号のシリーズが並ぶと、PACS の画面で区別しにくいため。IHE は定めていない）

## 検討した選択肢

- 同じ予約の2回目を、DTG が新しい Study Instance UID で作る：IHE RAD TF-2
  4.8.4.1.1.1 に反する。施設のローカルルールの形は、RIS の新しい予約で作れる
- 2回目を断るだけにする：Append Case を試せない
- `new_order` で、DTG が受付番号と Study Instance UID を作る：受付番号は RIS が発番
  するもので、上と同じく IHE に反する
- MPPS を使う設定のときだけ撮影済みにする：画面のボタンの振る舞いが設定で変わり、
  分かりにくい

## 結果

- 1回目の撮影と追加の撮影を区別して作れ、RIS・PACS の Append Case の扱いを試せる
- `new_order` では、RIS が撮り直しの予約を作れることが前提になる
- 同じ予約で「撮影」を2回押す今までの使い方はできなくなり、「追加撮影」を使う
- 撮影の記録の表が増える。前の版で撮った予約（Study Instance UID だけの記録）も、
  撮影済みとして扱う

## 出典

- DICOM PS3.4 F.7.2.2.2・F.7.2.2.3（MPPS の N-SET）
- IHE Radiology TF-2 Rev. 23.0：4.6.4.1.2.3.3（Append Case）、4.8.4.1.1.1
- IHE Radiology TF-2x Rev. 23.0：Appendix A、Table A.1-3、IHE-A.3.1〜A.3.7

## 関連

- ADR-0014（通常の経路は規格どおりに生成する）、ADR-0017（Study Instance UID は予約から
  転記する）、ADR-0020（MPPS）
- docs/spec/12_modality_emulator.md の 6.2・6.3・8.4、docs/spec/12a_web_screens_and_cli.md
  の 10.4・10.5・11.4
