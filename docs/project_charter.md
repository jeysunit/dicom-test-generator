# 目的と範囲

## 1. 目的

DICOM Test Data Generator（リポジトリ名 `dicom-test-generator`。以下 DTG）は、
架空の患者の架空の検査の DICOM 画像を作成するテスト用のツールである。用途は、
PACS・RIS・ビューアを、本物の患者のデータを使わずにテストすることである。補助の
機能として、作成した画像を PACS へ送信する、ワークリストを取得して予約の内容で
作成する、Web 画面・GUI から操作する、ができる（モダリティのように振る舞える）。

1. **DICOM 画像の作成（主な機能）**：多様なメタデータを持つ DICOM ファイルを作成
   する。規格どおりのデータと、あえて規格に違反したデータ（異常のデータ）の両方を
   作成できる
2. **補助の機能**：作成した画像の PACS への送信、ワークリストの取得と予約の内容での
   作成、保管確認、MPPS、Web 画面・GUI からの操作

DTG は診療のためではなく、システムのテストに使う。機能はテストに必要な分だけに
する。

**生成するピクセルデータは合成したもので、実際の医療画像ではない。臨床には
使えない。**

## 2. 規格の前提

**DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。**
値・Type・長さ・文字コード・応答のステータスは原典（dicom.nema.org の PS3.x、
hl7.org、IHE の Technical Framework）で確認し、spec か ADR に規格の節番号を書く。

例外は1つある。DTG は、あえて規格に違反したデータを生成する機能（異常のデータ）を
持つ。前提を適用するのは「通常の経路」だけで、「異常のデータの経路」は対象外に
する（[ADR-0014](decisions/0014-separate-normal-and-abnormal-paths.md)）。

| 経路 | 条件 | 規格の前提 |
|------|------|------------|
| 通常の経路 | 異常のデータのレベルが `none` で、`abnormal.allow_invalid_sop_uid` を使わない生成 | 適用する。規格に合わない入力は生成の前に拒否し、生成する画像は規格どおりにする |
| 異常のデータの経路 | `abnormal.level` が `mild`・`moderate`・`severe` のときと、`abnormal.allow_invalid_sop_uid` を使うとき | 適用しない。ただし生成する違反は、[spec/02](spec/02_core_engine.md) の AbnormalGenerator で定義したものだけ |

詳細は [spec/06](spec/06_dicom_rules.md) の「通常の経路と異常のデータの経路」に
ある。

## 3. 範囲

| 機能 | 内容 | spec |
|------|------|------|
| DICOM ファイルの生成 | Study・Series・Instance の階層、UID（2.25 の形式）、マルチスライスの空間座標、Transfer Syntax の選択。病院・モダリティ別のテンプレート、患者マスターの情報、YAML の Job による設定 | [02](spec/02_core_engine.md)・[06](spec/06_dicom_rules.md)・[07](spec/07_job_schema.md) |
| 日本語の患者名 | Specific Character Set と、PN の英字・漢字・かなの表記 | [06](spec/06_dicom_rules.md) |
| ピクセルの生成 | 簡易モード（UID の文字列を描画する）と CT モード（16 ビットの HU 値）。どちらも実際の画像ではない | [02](spec/02_core_engine.md)・[06](spec/06_dicom_rules.md) |
| 異常のデータの生成 | 必須タグの欠落、VR の違反、文字数の超過、不正な UID、Pixel Data の欠落。レベル（none・mild・moderate・severe）で選ぶ | [02](spec/02_core_engine.md)・[06](spec/06_dicom_rules.md) |
| モダリティエミュレーター | ワークリスト（MWL）の取得、予約からの撮影、予約の無い緊急の患者の入力、C-STORE での送信、疎通確認（C-ECHO）、送信失敗時のキューと再送、保管確認（Storage Commitment）、MPPS | [12](spec/12_modality_emulator.md) |
| 装置プロファイル | 装置のコンフォーマンスステートメントの内容を転記し、その装置の DICOM の出力（製造元・機種・属性・プライベートタグ）をテンプレートに重ねて再現する | [13](spec/13_device_profiles.md) |
| CLI | 生成・検証・簡易生成と、モダリティエミュレーターの操作 | [04](spec/04_cli.md)・[12a](spec/12a_web_screens_and_cli.md) |
| Web 画面 | ワークリスト・撮影・PACS・設定の画面（FastAPI・Jinja2・HTMX） | [12a](spec/12a_web_screens_and_cli.md) |
| デスクトップ画面 | PySide6 の基本の生成機能だけ。機能は追加しない | [05](spec/05_gui.md) |

## 4. 範囲に入れないもの

- 診断を目的とした、実際の医療画像の生成
- 本番の PACS への接続
- 画像を受信して保存すること。受信は PACS の役目で、テストの相手は利用者が
  用意する（[ADR-0013](decisions/0013-remove-storage-scp.md)）
- ワークリストの SCP（RIS の役）、保管確認と MPPS の SCP。テストの中だけで起動
  する（[ADR-0021](decisions/0021-test-only-commitment-and-mpps-peers.md)）
- 患者のプライバシーデータの管理
- 医療機器としての認証の取得
- Query/Retrieve（C-MOVE・C-GET）の SCU、HL7 の受信と送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査ログなど）

CT 以外のモダリティ（MR・CR・DX・US など）はまだ実装していない
（[roadmap.md](roadmap.md)）。

## 5. 想定する利用者

- 医療システムの開発者：DICOM の取り込み機能や、ワークリストの連携のデバッグ
- QA エンジニア：異常のデータを含むテストケースの作成
- 医療 IT の開発者：製品の検証用のデータの生成

## 6. 開発の方針

- **仕様を先に決めてから実装する。** 手順は [README.md](README.md) の「書き方」
- **機能は追加するより減らす。** テストの相手として不要な機能は追加しない
- **層を分ける。** UI は Service を経由して Core を使う。依存は上から下への一方向
  （[architecture.md](architecture.md)）
- **Core は単体でテストできるようにする。** 通信・ファイル・ログを持たない処理は
  Core に置く

## 7. ライセンス

MIT License
