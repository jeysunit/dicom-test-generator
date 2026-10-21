# ADR-0013: 受信の機能（Storage SCP）を外す

- 状態：採用
- 日付：2026-10-20
- 作成日：2026-10-20

ADR-0009 と ADR-0010 が決めた Storage SCP（手元で画像を受け取る側）を外す。
両 ADR は歴史的な記録として残し、状態を Superseded にした。

## 背景

Storage SCP は Phase 1.5 で、生成した画像を手元で受け取って保存する側として
作った（`app/scp/`、CLI の `scp start`、設定の `storage_scp:`、
`spec/11_storage_scp.md`）。その後、この道具の目的を
モダリティのダミー（ADR-0011）に定めた。モダリティは画像を作って送る側であり、
受ける側ではない。

受ける側を持ち続けると、次の費用がかかる。

- 受信の安全（相手の値でファイルを書く）を守る実装と試験が要る。ADR-0010 の
  7 は、待ち受けの既定を手元に絞る修正だった
- 保管の確認や MPPS の受け手まで広げたくなる（ADR-0011 の spec/12 8.4.2 は、
  その拡張を断っている）
- 文書が「作って送る」と「受ける」の二つの目的を持ち、読み手が迷う

## 決定

1. **受信の機能を外す。** 理由：受信は PACS の役目で、モダリティの擬態という
   目的の外にある。試験の相手は使う側が自分で用意する
2. 原則は「機能は足すより削る」（spec/12a の 10 章の冒頭と同じ向き）
3. 外すもの：
   - `app/scp/`（`server.py`・`handler.py`・`models.py`）
   - CLI の `scp start`
   - 設定の `storage_scp:` の節
   - 例外 `SCPError`・`SCPConfigError`・`SCPStoreError`
   - `spec/11_storage_scp.md`
   - 受信だけを確かめていた試験（`tests/scp/` の 4 ファイル、29 件）
4. 残すもの：
   - 送る側の C-STORE・C-ECHO（SCU）
   - 保管の確認の結果を受ける小さな待ち受け（`modality.listen`。N-EVENT-REPORT
     と C-ECHO だけを受ける。SCU の手順の一部）
   - 試験の中で立てる偽の相手（`tests/modality_peers.py`。ワークリストの SCP・
     Storage の SCP・保管の確認の SCP・MPPS の SCP）
   - 偽の相手を使う統合の試験。受け手を `app/scp` から偽の相手に替え、
     予約の値が画像に写る期待は変えない

## 影響

### 良い点

- 目的（モダリティの擬態）に合わない面が無くなり、文書も短くなる
- 受信の安全に関わる面（相手の値でファイルを書く）が無くなる

### 悪い点

- この道具だけで「撮る→送る→受ける」を閉じた試験にはできなくなる。
  手元で受けたいときは、Orthanc など別の PACS を使う
- `python -m app.cli scp start` を使っていた利用者は、別の受け手に移る

## 変更対象

- `spec/11_storage_scp.md`（削除）
- `spec/12_modality_emulator.md`（9.2 の層の図ほか）・`spec/01_architecture.md`・
  `spec/00_overview.md`・`spec/04_cli.md`・`spec/08_error_handling.md`
- `README.md`・`WORKFLOW.md`・`AI_DEVELOPMENT_RULES.md`
- `app/scp/`・`app/cli/`・`app/core/exceptions.py`・`config/app_config.yaml`
- `tests/scp/`・`tests/integration/test_modality_flow.py`

## 関連する決定

- [ADR-0009: Phase 1.5（Storage SCP）の推奨実装順序を明確化](0009-phase-1-5-ordering.md)
- [ADR-0010: Storage SCP の運用仕様を固定](0010-storage-scp-operational-decisions.md)
- [ADR-0011: モダリティのダミーにする](0011-modality-emulator.md)
