# Tasks

## 1. 設定

- [ ] 1.1 `stations`・`default_station` を読むテスト（2つの装置・重複・今の形・両方を書いた形・VR に合わない値）を `tests/modality/test_config_and_queue.py` に足し、`app/modality/config.py` を実装する
- [ ] 1.2 `config/app_config.yaml` の例に装置の一覧を、例の名前とループバックのアドレスだけで書く

## 2. 選んだ装置の記録と通信

- [ ] 2.1 選んだ装置を状態の保存先に記録・読み込みし、設定に無い表示名なら既定に戻すことをテストで確かめる
- [ ] 2.2 C-FIND・C-STORE・C-ECHO・MPPS・N-ACTION の Calling AE Title が選んだ装置になることを、`tests/modality_peers.py` のスタブで確かめるテストを足して実装する
- [ ] 2.3 送信キューと MPPS の行に AE タイトルの列を足し（既存の DB の移行を含む）、切り替えた後の再送が作ったときの AE タイトルで送ることをテストで確かめる
- [ ] 2.4 保管確認の待ち受けが、設定の装置の AE タイトルあてを受けてそれ以外を理由 7 で拒否し、要求を送った装置あての結果だけを採ることをテストで確かめる
- [ ] 2.5 理由 3 の拒否の知らせをテストで確かめる（スタブの SCP に Calling AE Title を拒否させる）

## 3. 画像

- [ ] 3.1 選んだ装置の Station Name と Source Application Entity Title が画像に入り、Station Name が空なら今の優先順の値になることを確かめるテストを足して実装する

## 4. 画面と CLI

- [ ] 4.1 情報バーに装置の選択を置き、切り替え・撮影の最中の拒否・再起動の後も残ることを `tests/web/` で確かめる
- [ ] 4.2 CLI に `--station` を足し、そのコマンドだけに効くことと、設定に無い名前の終了コードをテストで確かめる
- [ ] 4.3 設定の画面に装置の一覧と、相手の側に AE タイトルを登録する旨を出す

## 5. 文書

- [ ] 5.1 ADR（装置の切り替えと Station Name の優先順）を template.md から作り、一覧に足す
- [ ] 5.2 spec 12 の 4・6.2・8・12 章、12a の 10.3・10.4・10.7・11 章、13 の Station Name、usage.md を直し、`python -m pytest -q`・ruff・mypy・markdownlint・`scripts/check_doc_dates.py` が合格することを確かめる
- [ ] 5.3 開発の環境の Orthanc に2つの AE タイトルを登録し、画面で切り替えて送信と保管確認が通ること、登録していない AE タイトルで拒否の知らせが出ることを確かめる
