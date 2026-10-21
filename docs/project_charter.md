# 目的と範囲

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 1. 目的

DICOM Test Data Generator（リポジトリ名 `dicom-test-generator`。以下 DTG）は、
CT などのモダリティとして振る舞い、架空の患者の DICOM 画像を作って PACS へ送る
試験用のツールである。RIS・PACS・ビューア・画像の取り込みシステムを、
本物の患者のデータを使わずに試すために使う。

1. 受け取る側のシステムの試験に使う、多様なメタデータを持つ DICOM ファイルを
   作る。規格どおりのデータと、あえて規格に違反したデータ（異常のデータ）の
   両方を作れる
2. モダリティの振る舞い（ワークリストの取得、予約に沿った撮影、画像の送信、
   保管確認、MPPS）をエミュレートし、受け取る側をローカルで試せるようにする

DTG は診療のためではなく、システムの試験でモダリティの代わりに使う。
機能は試験に要る分だけにする。

**作るピクセルデータは合成したもので、実際の医療画像ではない。臨床には
使えない。**

## 2. 規格の前提

**DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。**
値・Type・長さ・文字コード・応答の状態は原典（dicom.nema.org の PS3.x、
hl7.org、IHE の Technical Framework）で確かめ、spec か ADR に規格の節番号を
書く。

例外は1つある。DTG は、あえて規格に違反したデータを作る機能（異常のデータ）を
持つ。前提が掛かるのは「ふつうの経路」だけで、「異常のデータの経路」は対象外に
する（[ADR-0014](decisions/0014-separate-normal-and-abnormal-paths.md)）。

| 経路 | いつ | 規格の前提 |
|------|------|------------|
| ふつうの経路 | 異常のデータのレベルが `none` で、`abnormal.allow_invalid_sop_uid` を使わない生成 | 掛かる。規格に合わない入力は生成の前に断り、作る画像は規格どおりにする |
| 異常のデータの経路 | `abnormal.level` が `mild`・`moderate`・`severe` のときと、`abnormal.allow_invalid_sop_uid` を使うとき | 掛からない。ただし作る違反は、[spec/02](spec/02_core_engine.md) の AbnormalGenerator で約束したものだけ |

細かい決まりは [spec/06](spec/06_dicom_rules.md) の「ふつうの経路と異常の
データの経路」にある。

## 3. 範囲

| 機能 | 内容 | spec |
|------|------|------|
| DICOM ファイルの生成 | 病院・モダリティ別のテンプレート、患者マスターの情報、1 スタディに複数のシリーズと画像、日本語とローマ字の切り替え、CT のリアルモードのピクセル | [02](spec/02_core_engine.md)・[06](spec/06_dicom_rules.md)・[07](spec/07_job_schema.md) |
| 異常のデータの生成 | レベル（none・mild・moderate・severe）別 | [02](spec/02_core_engine.md)・[06](spec/06_dicom_rules.md) |
| モダリティエミュレーター | ワークリスト（MWL）の取得、予約からの撮影、C-STORE での送信、失敗した送信の再送、保管確認（Storage Commitment）、MPPS | [12](spec/12_modality_emulator.md) |
| 装置のプロファイル | ある装置の DICOM の出し方（製造元・機種・属性・プライベートタグ）をテンプレートに重ねる | [13](spec/13_device_profiles.md) |
| CLI | 生成・検証・簡易生成と、モダリティエミュレーターの操作 | [04](spec/04_cli.md)・[12a](spec/12a_web_screens_and_cli.md) |
| Web 画面 | ワークリスト・撮影・PACS・設定の画面（FastAPI・Jinja2・HTMX） | [12a](spec/12a_web_screens_and_cli.md) |
| デスクトップの画面 | PySide6 の基本の生成の流れだけ。機能は足さない | [05](spec/05_gui.md) |

## 4. 範囲に入れないもの

- 診断を目的とした、実際の医療画像の生成
- 本番の PACS への接続
- 画像を受信して保存すること。受信は PACS の役目で、試験の相手は使う側が
  用意する（[ADR-0013](decisions/0013-remove-storage-scp.md)）
- ワークリストの SCP（RIS の役）、保管確認と MPPS の SCP。試験の中だけで立てる
  （[ADR-0021](decisions/0021-test-only-commitment-and-mpps-peers.md)）
- 患者のプライバシーデータの管理
- 医療機器としての認証の取得
- Query/Retrieve（C-MOVE・C-GET）の SCU、HL7 の受信と送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査の記録など）

CT 以外のモダリティ（MR・CR・DX・US など）はまだ作っていない
（[roadmap.md](roadmap.md)）。

## 5. 想定する利用者

- 医療システムの開発者：DICOM の取り込み機能や、ワークリストの連携のデバッグ
- QA エンジニア：異常のデータを含む試験ケースの作成
- 医療 IT の開発者：製品の検証用のデータの生成

## 6. 開発の方針

- **仕様を先に固めてから実装する。** 今どう動くかは [spec/](spec/)、
  なぜそう決めたかは [decisions/](decisions/README.md) に書く
- **機能は足すより削る。** 試験の相手として要らない機能は足さない
- **層を分ける。** UI は Service を通して Core を使う。依存は上から下の一方向
  （[architecture.md](architecture.md)）
- **Core は単体で試験できるようにする。** 通信・ファイル・ログを持たない処理は
  Core に置く

## 7. ライセンス

MIT License
