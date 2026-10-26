# 設計判断（ADR）

ADR の一覧と、ADR に固有の書き方です。ドキュメントに共通の書き方は
[docs/README.md の「書き方」](../README.md#書き方) にあります。

## 一覧

| 番号 | 題 | 状態 |
|------|----|------|
| [0001](0001-core-library-first.md) | Core Library First | 採用 |
| [0002](0002-yaml-job-configuration.md) | YAML Job Configuration | 採用 |
| [0003](0003-pyside6-gui.md) | PySide6 GUI | 置き換え済み（ADR-0022） |
| [0004](0004-uuid-2-25-uid.md) | UUID 2.25 UID | 採用 |
| [0005](0005-pixel-modes.md) | Pixel Modes | 採用 |
| [0006](0006-threading-model.md) | Threading Model | 置き換え済み（ADR-0022） |
| [0007](0007-patient-size-in-centimeters.md) | Patient Size（身長）の単位を cm に変更 | 採用 |
| [0008](0008-patient-age-derived-from-dates.md) | PatientAge を birth_date / study_date から算出する | 採用 |
| [0009](0009-phase-1-5-ordering.md) | Phase 1.5（Storage SCP）の推奨実装順序を明確化 | 置き換え済み（ADR-0013） |
| [0010](0010-storage-scp-operational-decisions.md) | Storage SCP の運用仕様（重複処理・停止・テスト）を固定 | 置き換え済み（ADR-0013） |
| [0011](0011-modality-emulator.md) | モダリティエミュレーターにする（SCU・Web 画面。既存の PySide6 の GUI の扱いは ADR-0022 が置き換えた） | 採用 |
| [0012](0012-device-profiles.md) | 装置プロファイルで装置の出力を再現する（仕組みは公開・実在の装置のプロファイルは非公開） | 採用 |
| [0013](0013-remove-storage-scp.md) | 受信の機能（Storage SCP）を削除する | 採用 |
| [0014](0014-separate-normal-and-abnormal-paths.md) | 通常の経路は規格どおりに生成し、規格の違反は異常のデータの経路で定めたものだけを生成する | 採用 |
| [0015](0015-no-explicit-vr-big-endian.md) | 廃止された Explicit VR Big Endian は生成しない | 採用 |
| [0016](0016-generic-template-names.md) | 公開のテンプレートと例の装置プロファイルに商用製品の名前を使わない | 採用 |
| [0017](0017-copy-study-instance-uid-from-worklist.md) | Study Instance UID は予約から転記し、予約に無いときだけ生成する | 採用 |
| [0018](0018-stop-on-unrepresentable-characters.md) | 画像の文字コードで表現できない文字があれば、その画像を書き出さずに停止する | 採用 |
| [0019](0019-storage-commitment-result-path.md) | 保管確認の結果は別の Association で受けることを既定にし、CLI では自動で要求しない | 採用 |
| [0020](0020-mpps-optional-with-retry-queue.md) | MPPS を送信できなくても撮影を止めず、未送信の通知はキューに残して再送する | 採用 |
| [0021](0021-test-only-commitment-and-mpps-peers.md) | 保管確認と MPPS の SCP は、テストの中だけで起動する | 採用 |
| [0022](0022-remove-desktop-gui.md) | PySide6 のデスクトップ画面を削除し、ファイルの作成は CLI に任せる | 採用 |
| [0023](0023-switch-own-station.md) | 名乗る装置を設定に複数書き、画面と CLI で切り替える | 採用 |
| [0024](0024-exam-once-and-retake.md) | 予約での撮影は1回で撮影済みにし、撮り直しの形は設定で選ぶ | 採用 |
| [0025](0025-exam-routines.md) | 撮影は既定で予約に当てたルーチンの並びと枚数で行う | 採用 |
| [0026](0026-container-image-distribution.md) | Docker のイメージを主な配布の形にし、タグの push と手動のときに GHCR に公開する | 採用 |
| [0027](0027-emergency-append.md) | 緊急の患者の追加撮影は、前の撮影の Study Instance UID と同じ患者を CLI で指定したときだけ受ける | 採用 |
| [0028](0028-shared-ui-kit-css.md) | 画面の CSS は 3 製品で共通の ui-kit の写しを読み、DTG の CSS には差分だけを書く | 採用 |
| [0029](0029-unknown-patient-emergency-input.md) | 身元不明の患者は、仮の ID と空の英字の氏名で撮れるようにする | 採用 |
| [0030](0030-mr-images.md) | MR の画像は、シリーズのモダリティで MR Image Storage として作る | 採用 |
| [0031](0031-dose-report-sr.md) | CT の線量の報告は、線量の画面のほかに X-Ray Radiation Dose SR のシリーズでも作れる | 採用 |
| [0032](0032-pet-ct-studies.md) | PET/CT の検査は、同じ Study に CT と PT のシリーズを入れて作る | 採用 |

0001〜0013 は、この形式を決める前に書いたものです。冒頭の行をこの形式に
そろえ、本文は語の置き換えだけにとどめています。

## 書き方

- 新しい ADR は [template.md](template.md) をコピーして書きます。ファイル名は
  `NNNN-英語の-kebab-case.md` で、番号は続きから振ります
- 冒頭は「状態」「作成日」「最終更新日」の3行だけにします。状態は 提案・採用・
  廃止・置き換え済み（ADR-NNNN）のどれかです。作成日はファイルを作成した日、
  最終更新日はファイルを最後に変更した日です。日付の行を持つのは ADR だけです
- ADR を変更したら、最終更新日をその日にします。記入漏れは
  `python scripts/check_doc_dates.py origin/main..HEAD` で検出でき、CI も PR の
  ときに実行します
- 必須の節は 背景・決定・検討した選択肢・結果 です。決めないこと・
  見直す条件・出典・関連は、必要なときだけ書きます
- 長さは A4 で1〜2枚に収めます
- 採用した ADR の本文は書き換えません。判断を変えるときは新しい ADR を作成し、
  古い ADR の状態の行を「置き換え済み（ADR-NNNN）」に変更します
- ADR を追加したら、この一覧に1行追加します。一覧は 6 本以上で必須です
