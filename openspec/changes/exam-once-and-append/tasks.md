# Tasks

## 0. 設定

- [ ] 0.1 `modality.retake_mode`（`append`・`new_order`、既定 `append`）を読むテスト（書かない・2つの値・設定に無い値）を足し、`app/modality/config.py` と `config/app_config.yaml` の例を実装する

## 1. 撮影済みの記録

- [ ] 1.1 予約ごとの撮影の記録（Study Instance UID・Study Date・Study Time・Study Description・シリーズの数）を `app/modality/queue.py` に足し、今の `generated_study_uids` の行を移すテストを書いて実装する
- [ ] 1.2 撮影が終わったら撮影済みにし、撮影が止まったら記録しないことを `tests/modality/test_service.py` で確かめる

## 2. 撮影と追加撮影

- [ ] 2.1 撮影済みの予約での通常の撮影を断るテスト（画面・CLI・終了コード）を足して実装する
- [ ] 2.2 追加撮影の依頼を足し、Study Instance UID・受付番号・Request Attributes Sequence が同じで、Series Instance UID が新しく、Study Date・Time・Description が最初の撮影の値で、Series Number が続きになることをテストで確かめる
- [ ] 2.3 MPPS を使う設定で、追加撮影が新しい MPPS の SOP Instance を作り、1回目の MPPS に N-SET を送らないことを `tests/modality/test_mpps_scu.py` のスタブで確かめる
- [ ] 2.4 予約に Study Instance UID が無いとき、追加撮影が1回目に作った UID を使うことを確かめる

## 3. 画面と CLI

- [ ] 3.1 撮影の画面で、撮影済みの予約の「撮影」「撮影して送る」を押せなくし、`append` では「追加撮影」を、`new_order` では「撮り直しの予約が要ります」の知らせだけを出す。両方の設定を `tests/web/` で確かめる
- [ ] 3.2 ワークリストの一覧に「撮影済み」の印を付ける
- [ ] 3.3 CLI の `exam --from-worklist ... --append` を足し、撮影済みでない予約と `new_order` で `--append` を指定したときに断ることをテストで確かめる
- [ ] 3.4 `new_order` で、RIS の撮り直しの予約（別の受付番号・Study Instance UID）をワークリストのスタブで返し、取得し直して撮ると新しい予約の値で画像と MPPS が作られることを確かめる

## 4. 文書

- [ ] 4.1 ADR（撮影済みの扱いと撮り直しの2つの形。既定を `append` にし、どちらの形でも DTG が新しい Study Instance UID・受付番号を作らない理由）を作り、一覧に足す
- [ ] 4.2 spec 12 の 6.2・6.3・8.4、12a の 10.4・10.5・10.8・11.4、usage.md を直し、`python -m pytest -q`・ruff・mypy・markdownlint・`scripts/check_doc_dates.py` が合格することを確かめる
- [ ] 4.3 開発の環境で、撮影して送った後にボタンが押せないこと、追加撮影の画像が PACS の同じ Study に新しいシリーズとして入ることを確かめる
