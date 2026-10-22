# Tasks

## 1. 撮影済みの記録

- [ ] 1.1 予約ごとの撮影の記録（Study Instance UID・Study Date・Study Time・Study Description・シリーズの数）を `app/modality/queue.py` に足し、今の `generated_study_uids` の行を移すテストを書いて実装する
- [ ] 1.2 撮影が終わったら撮影済みにし、撮影が止まったら記録しないことを `tests/modality/test_service.py` で確かめる

## 2. 撮影と追加撮影

- [ ] 2.1 撮影済みの予約での通常の撮影を断るテスト（画面・CLI・終了コード）を足して実装する
- [ ] 2.2 追加撮影の依頼を足し、Study Instance UID・受付番号・Request Attributes Sequence が同じで、Series Instance UID が新しく、Study Date・Time・Description が最初の撮影の値で、Series Number が続きになることをテストで確かめる
- [ ] 2.3 MPPS を使う設定で、追加撮影が新しい MPPS の SOP Instance を作り、1回目の MPPS に N-SET を送らないことを `tests/modality/test_mpps_scu.py` のスタブで確かめる
- [ ] 2.4 予約に Study Instance UID が無いとき、追加撮影が1回目に作った UID を使うことを確かめる

## 3. 画面と CLI

- [ ] 3.1 撮影の画面で、撮影済みの予約の「撮影」「撮影して送る」を押せなくし、「追加撮影」を出す。`tests/web/` で確かめる
- [ ] 3.2 ワークリストの一覧に「撮影済み」の印を付ける
- [ ] 3.3 CLI の `exam --from-worklist ... --append` を足し、撮影済みでない予約で `--append` を指定したときの扱いをテストで確かめる

## 4. 文書

- [ ] 4.1 ADR（撮影済みの扱いと追加撮影。Append Case を選び、同じ予約で新しい Study を作らない理由）を作り、一覧に足す
- [ ] 4.2 spec 12 の 6.2・6.3・8.4、12a の 10.4・10.5・10.8・11.4、usage.md を直し、`python -m pytest -q`・ruff・mypy・markdownlint・`scripts/check_doc_dates.py` が合格することを確かめる
- [ ] 4.3 開発の環境で、撮影して送った後にボタンが押せないこと、追加撮影の画像が PACS の同じ Study に新しいシリーズとして入ることを確かめる
