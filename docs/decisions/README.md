# 設計の判断（ADR）

- 作成日：2026-10-22
- 最終更新日：2026-10-22

ADR（Architecture Decision Record）は、なぜその設計にしたかを1件ずつ残す記録です。
今どう動くかは [spec](../spec/) に書き、ここには判断と理由だけを書きます。

## 一覧

| 番号 | 題 | 状態 |
|------|----|------|
| [0001](0001-core-library-first.md) | Core Library First | 採用 |
| [0002](0002-yaml-job-configuration.md) | YAML Job Configuration | 採用 |
| [0003](0003-pyside6-gui.md) | PySide6 GUI（モダリティの画面は ADR-0011 が置き換えた） | 採用 |
| [0004](0004-uuid-2-25-uid.md) | UUID 2.25 UID | 採用 |
| [0005](0005-pixel-modes.md) | Pixel Modes | 採用 |
| [0006](0006-threading-model.md) | Threading Model | 採用 |
| [0007](0007-patient-size-in-centimeters.md) | Patient Size（身長）の単位を cm に変更 | 採用 |
| [0008](0008-patient-age-derived-from-dates.md) | PatientAge を birth_date / study_date から算出する | 採用 |
| [0009](0009-phase-1-5-ordering.md) | Phase 1.5（Storage SCP）の推奨実装順序を明確化 | 置き換え済み（ADR-0013） |
| [0010](0010-storage-scp-operational-decisions.md) | Storage SCP の運用仕様（重複処理・停止・テスト）を固定 | 置き換え済み（ADR-0013） |
| [0011](0011-modality-emulator.md) | モダリティのダミーにする（SCU・ウェブの画面） | 採用 |
| [0012](0012-device-profiles.md) | 装置のプロファイルで装置の出し方を擬態する（仕組みは公開・写しは非公開） | 採用 |
| [0013](0013-remove-storage-scp.md) | 受信の機能（Storage SCP）を外す | 採用 |
| [0014](0014-separate-normal-and-abnormal-paths.md) | ふつうの経路は規格どおりに作り、規格の違反は異常のデータの経路で約束したものだけを作る | 採用 |
| [0015](0015-no-explicit-vr-big-endian.md) | 廃止の Explicit VR Big Endian は作らない | 採用 |
| [0016](0016-generic-template-names.md) | 公開のテンプレートと例のプロファイルに商用の製品の名前を使わない | 採用 |
| [0017](0017-copy-study-instance-uid-from-worklist.md) | Study Instance UID は予約から写し、予約に無いときだけ作る | 採用 |
| [0018](0018-stop-on-unrepresentable-characters.md) | 画像の文字コードで表せない字があれば、その画像を書かずに止める | 採用 |
| [0019](0019-storage-commitment-result-path.md) | 保管確認の結果は別の Association で受けるのを既定にし、CLI では自動で求めない | 採用 |
| [0020](0020-mpps-optional-with-retry-queue.md) | MPPS は送れなくても撮影を止めず、送れない通知はキューに残して送り直す | 採用 |
| [0021](0021-test-only-commitment-and-mpps-peers.md) | 保管確認と MPPS の SCP は、試験の中にだけ立てる | 採用 |

0001〜0013 は、この形を決める前に書いたものです。冒頭の行だけをこの形に
そろえ、本文は書いたときのまま残しています。

## 書き方

- 新しい ADR は [template.md](template.md) を写して書きます。ファイル名は
  `NNNN-英語の-kebab-case.md` で、番号は続きから振ります
- 冒頭は「状態」「日付」「作成日」の3行だけにします。状態は 提案・採用・廃止・
  置き換え済み（ADR-NNNN）のどれかです。日付は今の状態になった日、作成日は
  ファイルを作った日です
- 必須の節は 背景・決定・検討した選択肢・結果 です。決めないこと・
  見直す条件・出典・関連は、要るときだけ書きます
- 長さは A4 で1〜2枚に収めます
- 採用した ADR の本文は書き換えません。判断を変えるときは新しい ADR を起こし、
  古い ADR の状態の行を「置き換え済み（ADR-NNNN）」に直します
- ADR を足したら、この一覧に1行足します
