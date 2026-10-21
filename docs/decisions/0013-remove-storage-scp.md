# ADR-0013: 受信の機能（Storage SCP）を削除する

- 状態：採用
- 作成日：2026-10-20
- 最終更新日：2026-10-22

ADR-0009 と ADR-0010 が決めた Storage SCP（ローカルで画像を受信する側）を削除する。
両 ADR は過去の記録として残し、状態を Superseded にした。

## 背景

Storage SCP は Phase 1.5 で、生成した画像をローカルで受信して保存する側として
作成した（`app/scp/`、CLI の `scp start`、設定の `storage_scp:`、
`spec/11_storage_scp.md`）。その後、このツールの目的を
モダリティエミュレーター（ADR-0011）に定めた。モダリティは画像を生成して送信する
側であり、受信する側ではない。

受信側を持ち続けると、次のコストがかかる。

- 受信の安全（相手の値でファイルを書き込む）を守る実装とテストが必要になる。
  ADR-0010 の 7 は、待ち受けの既定をループバックに限定する修正だった
- 保管確認や MPPS の受信側まで広げたくなる（ADR-0011 の spec/12 8.4.2 は、
  その拡張を採用していない）
- 文書が「生成して送信する」と「受信する」の二つの目的を持ち、読み手が迷う

## 決定

1. **受信の機能を削除する。** 理由：受信は PACS の役目で、モダリティの再現という
   目的の外にある。テストの相手は利用者が自分で用意する
2. 原則は「機能は追加するより減らす」（spec/12a の 10 章の冒頭と同じ方針）
3. 削除するもの：
   - `app/scp/`（`server.py`・`handler.py`・`models.py`）
   - CLI の `scp start`
   - 設定の `storage_scp:` の節
   - 例外 `SCPError`・`SCPConfigError`・`SCPStoreError`
   - `spec/11_storage_scp.md`
   - 受信だけを確認していたテスト（`tests/scp/` の 4 ファイル、29 件）
4. 残すもの：
   - 送信側の C-STORE・C-ECHO（SCU）
   - 保管確認の結果を受ける小さな待ち受け（`modality.listen`。N-EVENT-REPORT
     と C-ECHO だけを受ける。SCU の手順の一部）
   - テストの中で起動するスタブ（`tests/modality_peers.py`。ワークリストの SCP・
     Storage の SCP・保管確認の SCP・MPPS の SCP）
   - スタブを使う統合テスト。受信側を `app/scp` からスタブに替え、
     予約の値が画像に転記されるという期待は変えない

## 影響

### 良い点

- 目的（モダリティの再現）に合わない部分が無くなり、文書も短くなる
- 受信の安全に関わる部分（相手の値でファイルを書き込む）が無くなる

### 悪い点

- このツールだけで「撮影→送信→受信」を閉じたテストにはできなくなる。
  ローカルで受信したいときは、Orthanc など別の PACS を使う
- `python -m app.cli scp start` を使っていた利用者は、別の受信側に移行する

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
- [ADR-0011: モダリティエミュレーターにする](0011-modality-emulator.md)
