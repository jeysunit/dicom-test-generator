# 12. モダリティエミュレーター

- 作成日：2026-10-18
- 最終更新日：2026-10-22

この文書は、モダリティエミュレーターの通信・予約の写し方・文字コード・送信・
層と配置・設定・ログ・既知の制約を書く。Web 画面と CLI は
[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) にある。

| 文書 | 章 |
|------|----|
| この文書（spec/12） | 1〜9 章、12〜15 章 |
| [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) | 10 章（Web 画面）、11 章（CLI） |

章の番号は、コード・試験・設定のコメントが番号で参照しているため、2つの文書を
通して振っている。本文の「10.5」のような番号だけの参照は、上の表の文書の章を
指す。

## 要約

DTG は、本物のモダリティと同じ順で動く。ワークリストを取得し
（C-FIND MWL の SCU）、予約の値を写した画像を作り、PACS へ送る
（C-STORE の SCU）。例外は3つある。

1. 予約なしの「緊急の患者」は、値を手で入れ、IHE の予約なしの形に従う
2. 保管確認（Storage Commitment の SCU）は選べる形にする
3. MPPS（N-CREATE・N-SET の SCU）は、相手が受けるときだけ使う

画面は Web 画面（サーバー側で描く。FastAPI・Jinja2・HTMX・Tailwind CSS）で
作る。同じ操作を CLI でも行え、自動の試験から使える。

DTG は診療のためではなく、システムの試験でモダリティの代わりに使う。機能は
少なくてよい。

設計の判断：[ADR-0011](../decisions/0011-modality-emulator.md)・
[ADR-0017](../decisions/0017-copy-study-instance-uid-from-worklist.md)・
[ADR-0018](../decisions/0018-stop-on-unrepresentable-characters.md)・
[ADR-0019](../decisions/0019-storage-commitment-result-path.md)・
[ADR-0020](../decisions/0020-mpps-optional-with-retry-queue.md)・
[ADR-0021](../decisions/0021-test-only-commitment-and-mpps-peers.md)

> **Not for Diagnostic Use / 非医療機器。** 生成する画素は合成で、臨床に
> 使えない。本番の PACS への接続は範囲の外。試験用の PACS・RIS にだけつなぐ。

---

## 1. 目的と範囲

### 目的

PACS・RIS・ビューアの試験で、モダリティの役を DTG に任せる。本物の装置を
使わずに、次の流れを繰り返し流せるようにする。

```text
RIS（ワークリスト）→ モダリティ → PACS
  ワークリストを取得 → 予約を選ぶ → 撮る（合成の画像）→ 送る → 確かめる
```

### 範囲に入れるもの

- C-FIND（Modality Worklist）の SCU
- C-STORE の SCU、C-ECHO の SCU
- Storage Commitment Push Model の SCU（選べる）
- MPPS（Modality Performed Procedure Step）の SCU（選べる）
- Web 画面（ワークリスト・撮影・PACS・設定）
- CLI（`worklist`・`exam`・`send`・`echo`・`queue`・`commit`・`mpps`）

### 範囲に入れないもの

- ワークリストの SCP（RIS の役）。試験の中だけで pynetdicom で立てる
- 画像を受信して保存する Storage SCP（PACS の役）。受信は PACS の役目で、
  試験の相手は使う側が用意する（[ADR-0013](../decisions/0013-remove-storage-scp.md)）
- Query/Retrieve（C-MOVE・C-GET）の SCU
- HL7 の受信・送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査の記録など）
- PySide6 のデスクトップの画面（[05_gui.md](05_gui.md)）の作り替え。
  扱いは [roadmap.md](../roadmap.md) の 3 章

### デスクトップの画面（spec/05）との関係

- [05_gui.md](05_gui.md) は、生成のための PySide6 の画面の仕様で、この文書の
  画面とは別のもの
- モダリティの画面はこの文書と 12a で決め、Web 画面にする
  （ADR-0011。ADR-0003 をモダリティの画面については置き換える）
- 生成の処理（テンプレート・異常のデータ・ピクセル）は共通で、どちらの画面も
  Service Layer を通して使う

---

## 2. 用語

| 言葉 | 意味 |
|------|------|
| 予約 | ワークリストの1件（Scheduled Procedure Step） |
| ワークリストの相手 | MWL の SCP（RIS・Orthanc の Worklists など） |
| 送り先 | Storage の SCP（PACS） |
| 撮る・撮影 | 予約の値で合成の画像を作ること（DTG では生成） |
| 緊急の患者 | 予約なしで撮る患者（IHE の Unscheduled Case） |
| 保管確認 | Storage Commitment。送った画像を相手が保管したかを問い合わせる |
| MPPS | 撮影の開始と終了を相手に通知する（N-CREATE・N-SET） |
| 送信キュー | 送る画像の列。状態は 8.2 |
| 状態の置き場 | 最後に取得したワークリスト、送信キュー、MPPS のキューを置くフォルダ（設定の `state_dir`） |

画面の言葉は、医療の現場の言葉を言い換えない。例：受付番号（Accession
Number）、検査、シリーズ、緊急、送信完了。

---

## 3. 操作の流れ

診療放射線技師の1日の操作に沿って書く。

```text
1. 朝、ワークリストの画面を開く
   └ 既定の条件（今日・自分の AE タイトル）でワークリストを取得する
2. 患者が来たら、一覧から予約を選ぶ
   └ 予約の値（氏名・ID・生年月日・受付番号など）を確かめる
   └ 必要なら「取得し直す」（その予約だけを最新にする。DD.1 の4つ目の例）
3. 撮影の画面で、テンプレート・シリーズ数・画像数・異常のデータを選ぶ
   └ 予約の値は読むだけ（書き換えない）
   └ MPPS を使うなら、撮影の開始で N-CREATE（IN PROGRESS）
4. 「撮影」で画像を作り、送信キューに入れる
   └ MPPS を使うなら、作り終わりで N-SET（COMPLETED）
5. PACS へ送る（撮影の画面の「撮影して送る」なら続けて送る）
   └ 送信完了・送信失敗を見る。失敗は再送
6. 保管確認を使うなら、結果（確認済・確認の失敗）を見る
7. 予約なしの患者が来たら「緊急の患者」で撮る
```

---

## 4. DICOM の通信

### 4.1 DTG が持つ役割

| 役割 | SOP Class | UID | 既定 |
|------|-----------|-----|------|
| Verification SCU | Verification | 1.2.840.10008.1.1 | 有効 |
| MWL SCU | Modality Worklist Information Model - FIND | 1.2.840.10008.5.1.4.31 | 有効 |
| Storage SCU | テンプレートの SOP Class（例: CT Image Storage） | 1.2.840.10008.5.1.4.1.1.2 | 有効 |
| Storage Commitment SCU | Storage Commitment Push Model | 1.2.840.10008.1.20.1 | 無効 |
| MPPS SCU | Modality Performed Procedure Step | 1.2.840.10008.3.1.2.3.3 | 無効 |

- 実装は pynetdicom の `AE`・`Association` の `send_c_echo`・
  `send_c_find`・`send_c_store`・`send_n_action`・`send_n_create`・
  `send_n_set` を使う（pynetdicom の公開の API。版は requirements.txt の範囲）
- 保管確認の結果（N-EVENT-REPORT）は、相手が**別の Association で**
  送ってくることが多い。受けるために、DTG は小さな待ち受け
  （N-EVENT-REPORT と、相手からの疎通確認の C-ECHO だけを受ける）を持つ。
  待ち受けは保管確認を有効にしたときだけ立てる（8.3.1）。画像を受信する
  機能ではない

### 4.2 Orthanc の対応

公開の資料とソースで確かめた（出典は 15 章）。

| 機能 | Orthanc | 根拠 |
|------|---------|------|
| C-ECHO・C-STORE・C-FIND（MWL）の SCP | 受ける | DICOM Conformance Summary（ソースの `DicomConformance.txt`） |
| Storage Commitment の SCP | 受ける（1.6.0 から。Push Model だけ。結果は非同期で、別の Association で返す） | Orthanc Book「DICOM storage commitment」 |
| MPPS（N-CREATE・N-SET）の SCP | **受けない** | Conformance Summary に無い。`CommandDispatcher.cpp` が扱う DIMSE は C-ECHO・C-STORE・C-FIND・C-MOVE・C-GET・N-ACTION・N-EVENT-REPORT だけで、ほかは `DIMSE_BADCOMMANDTYPE` |

したがって、**MPPS は相手が受けるときだけ使う**。既定は無効。Orthanc を相手に
するときは無効のままにする。有効にして相手が断ったら、撮影は止めず、MPPS の
失敗として画面と記録に出す。

Orthanc の保管確認では、要求してきたモダリティを `DicomModalities` に登録して
おく必要がある（結果を返す先の AE タイトル・ホスト・ポートを Orthanc が知るため。
Orthanc Book）。設定の画面に、その旨と DTG の待ち受けの AE タイトル・ポートを
出す。

---

## 5. ワークリストの取得

### 5.1 取得の条件（Matching Keys）

| 条件 | Tag | 既定 | 画面 | 出典 |
|------|-----|------|------|------|
| 予定の日（Scheduled Procedure Step Start Date） | (0040,0002) | 今日（範囲 `今日-今日` で送る） | 今日・明日・日付の指定・絞らない | RAD TF-2 Table 4.5-2 |
| モダリティ | (0008,0060) | テンプレートのモダリティ | 選ぶ・空 | 同上 |
| 予定の装置の AE タイトル（Scheduled Station AE Title） | (0040,0001) | 自分の AE タイトル | 自分・絞らない | 同上 |
| 患者 ID | (0010,0020) | 空 | 入力 | RAD TF-2 Table 4.5-1 |
| 患者の氏名 | (0010,0010) | 空 | 入力（各成分の末尾に `*` を足す） | 同上 |
| 受付番号 | (0008,0050) | 空 | 入力 | 同上 |
| Requested Procedure ID | (0040,1001) | 空 | CLI だけ | 同上 |

- 予定の日・モダリティ・AE タイトルは Scheduled Procedure Step
  Sequence (0040,0100) の中に入れる（PS3.4 K.6.1.2.2）
- 日付は範囲で送る。単一の値の日付の一致のしかたが相手によって違いうるため、
  IHE は範囲（`<今日>-<今日>`）を勧めている（RAD TF-2 4.5.4.1.2.1 の Note）
- 氏名の各成分の末尾に `*` を足す（同じ Note の勧め）。利用者が `*` を入れた
  ときは足さない
- 取得の条件の組は、DICOM PS3.17 DD.1 の例（日付と AE タイトル、日付と
  モダリティ、患者ごと）に合わせる

### 5.2 返してもらう値（Return Keys）

RAD TF-2 Table 4.5-3 で、SCU が R+・R+* の値をすべて求める。主なもの：

- Scheduled Procedure Step Sequence の中：Scheduled Station AE Title・
  Start Date・Start Time・Modality・Scheduled Performing Physician's
  Name・Scheduled Procedure Step ID・Scheduled Protocol Code Sequence・
  Scheduled Procedure Step Description
- Requested Procedure ID・Requested Procedure Description・
  Requested Procedure Code Sequence・Reason for the Requested Procedure
- Study Instance UID・Referenced Study Sequence
- Accession Number・Issuer of Accession Number Sequence・
  Requesting Physician・Referring Physician's Name
- Patient's Name・Patient ID・Issuer of Patient ID・Patient's Birth
  Date・Patient's Sex・Patient's Weight・Patient's Size
- Specific Character Set (0008,0005)
- Institution Name（返ってくれば）

### 5.3 問い合わせの文字コード

- 取得の条件がすべて ASCII なら、問い合わせに Specific Character Set を
  入れない（既定の文字セット。PS3.4 C.2.2.2）
- 氏名などに ASCII でない字があれば、設定の `worklist.query_character_set`
  （既定 `ISO_IR 192`。`jis`・`jis_kana` の値も選べる）で書き、その値を
  問い合わせの Specific Character Set に入れる
- 相手がその文字コードを扱わないと、一致のしかたは相手次第になる
  （PS3.4 C.2.2.2）。0 件のときは画面に「日本語の条件は相手の文字コードの扱いに
  左右されます。患者 ID か受付番号でも取得してください」と出す
- 画像の文字コードの `auto`（7 章）は、問い合わせには使わない

### 5.4 応答の扱い

- 応答の Specific Character Set を読み、値を Python の文字列に戻す
  （pydicom）。戻せない値は「読めない値」として画面に出し、その予約は撮影に
  進めない。写す Sequence の中の値（入れ子を含む）も確かめ、
  `ReferencedStudySequence>ReferencedSOPClassUID` のように `Sequence>属性` の
  形で名前を残す。Sequence の中の UID（VR が UI）は、UID の形（6.5）でなければ
  読めない値とする
- 一覧の1件ごとに、DTG の中だけで使う鍵（予約の鍵）を付ける。鍵は
  `Study Instance UID`・`Requested Procedure ID`・
  `Scheduled Procedure Step ID`・`Accession Number` をこの順に `|` で連ねた
  文字列（UTF-8）の SHA-1 の16進の先頭 10 桁。CLI の `--from-worklist <鍵>` で
  使う
- 最後に取得した結果を状態の置き場に保存する。CLI はこれを読む
- 相手が Pending を返し続けて決めた時間（既定 30 秒）を過ぎたら C-CANCEL を
  送り、受け取った分を「途中まで」として出す
- `exam --refresh`（その予約だけを取得し直す）のときは、時間の上限で途中までに
  なったら撮らずに `WorklistQueryError`（終了コード 5）で止める。ほかの取得の
  しかたは途中までを返す

### 5.5 応答の上限

**相手が返す応答は、受け取りながら数え、上限を超えたら C-CANCEL を送って
Association を切り、`WorklistQueryError`（終了コード 5）で止める。** 途中まで
受け取った分は出さない。例外は1つ：時間の上限（`timeout_seconds`）は 5.4 の
とおり C-CANCEL して「途中まで」を出す。

| 上限 | 設定（`modality.worklist`） | 既定 |
|------|------------------------------|------|
| 件数 | `max_results` | 1000 |
| 1件の大きさ（Implicit VR で書いたときのバイト数） | `max_item_bytes` | 256 KiB |
| 合計の大きさ | `max_total_bytes` | 16 MiB |
| C-CANCEL の後に返し続ける時間 | `timeout_seconds` と同じ長さ | 30 秒 |

- 上限は、その件を一覧に足す前に確かめる。1件の大きさは、pynetdicom が1件を
  受け取った後でしか量れない（受け取りの途中で止める手段が無い）。1件がメモリに
  載る大きさは pynetdicom の受け取りに任せる
- C-CANCEL の後も相手が返し続けたら、待つのは `timeout_seconds` の分だけにし、
  Association を切って `WorklistQueryError` にする

---

## 6. 予約から画像への値の写し方

### 6.1 決まり

**予約にある値は、そのまま写す。** 予約に無い値は、DTG が作るか空にする。
出典は IHE RAD TF-2x Appendix A の Table A.1-1（予約どおりの形）と
Table A.1-2（予約なしの形）。IHE は、モダリティが予約の値を画像のヘッダーに
入れることを求める（RAD TF-2 4.8.1・4.8.4.1.2）。

### 6.2 表

「写す」は予約の値をそのまま使う。「作る」は DTG が作る。

| 画像の属性 | Tag | 予約あり | 予約なし（緊急） | 出典 |
|------------|-----|----------|------------------|------|
| Specific Character Set | (0008,0005) | 「7. 文字コード」で決める | 設定の文字コード | PS3.4 K.6.1.3.1、PS3.3 C.12.1.1.2 |
| Patient's Name | (0010,0010) | 写す | 手で入れる | RAD TF-2 Table 4.5-3 |
| Patient ID | (0010,0020) | 写す | 手で入れる（仮の ID の案を出す） | 同上 |
| Issuer of Patient ID | (0010,0021) | 写す（あれば） | 空 | 同上 |
| Patient's Birth Date | (0010,0030) | 写す。**空なら空で写す**（6.3） | 手で入れる | 同上、PS3.4 Table K.6-1（Type 2） |
| Patient's Sex | (0010,0040) | 写す。**空なら空で写す**（6.3） | 手で入れる | 同上 |
| Patient's Weight | (0010,1030) | 写す（あれば。kg） | 出力しない（CLI では入れない） | 同上 |
| Patient's Size | (0010,1020) | 写す（あれば。DICOM の m の値をそのまま写す。内部の `Patient.size`（cm）は通さない） | 出力しない（CLI では入れない） | 同上、ADR-0007 |
| Patient's Age | (0010,1010) | 生年月日と検査日から算出。生年月日が空なら出さない | 同じ | ADR-0008 |
| Study Instance UID | (0020,000D) | **予約にあれば写す。無ければ作る**（2.25） | 作る | RAD TF-2x Table A.1-1・A.1-2、RAD TF-2 4.8.4.1.1.1、ADR-0017 |
| Accession Number | (0008,0050) | 写す | **空（長さ0）** | 同上（IHE-A.1.1） |
| Issuer of Accession Number Sequence | (0008,0051) | 写す（あれば） | 空 | Table A.1-1 |
| Referenced Study Sequence | (0008,1110) | 写す（あれば） | 出力しない | Table A.1-1 |
| Referring Physician's Name | (0008,0090) | 写す | 空 | RAD TF-2 Table 4.5-3 |
| Study ID | (0020,0010) | Requested Procedure ID | 作る（連番。`E` と 6 桁。状態の置き場の SQLite で数える） | Table A.1-1（IHE の勧め） |
| Study Description | (0008,1030) | Requested Procedure Description | 撮影の画面の入力 | この仕様の決め（慣習。IHE の表には無い） |
| Study Date・Time | (0008,0020)・(0008,0030) | 撮影した日時 | 同じ | この仕様の決め |
| Procedure Code Sequence | (0008,1032) | Requested Procedure Code Sequence を写す | 入れない | Table A.1-1 |
| Request Attributes Sequence | (0040,0275) | 1 項目を作り、下の値を写す | **属性を出力しない**（空の Sequence も置かない。Table A.1-2 の `n.a.`） | Table A.1-1・A.1-2 |
| >Requested Procedure ID | (0040,1001) | 写す | — | Table A.1-1 |
| >Requested Procedure Description | (0032,1060) | 写す | — | 同上 |
| >Scheduled Procedure Step ID | (0040,0009) | 写す | — | 同上 |
| >Scheduled Procedure Step Description | (0040,0007) | 写す | — | 同上 |
| >Scheduled Protocol Code Sequence | (0040,0008) | 写す | — | 同上 |
| >Reason for the Requested Procedure | (0040,1002) | 写す（あれば） | — | 同上 |
| Performed Procedure Step ID | (0040,0253) | 作る（連番。`PPS` と 6 桁） | 作る（同じ） | Table A.1-1（IHE-A.1.2） |
| Performed Procedure Step Start Date・Time | (0040,0244)・(0040,0245) | Study Date・Time と同じ | 同じ | Table A.1-1（IHE の勧め） |
| Performed Procedure Step Description | (0040,0254) | Study Description と同じ | 同じ | 同上 |
| Referenced Performed Procedure Step Sequence | (0008,1111) | MPPS を使うときだけ、その SOP Instance UID | 同じ | Table A.1-1（IHE-A.1.3） |
| Modality | (0008,0060) | テンプレートの値。予約の値と違えば撮影の画面で止める | テンプレートの値 | この仕様の決め |
| Institution Name | (0008,0080) | 写す（あれば）。無ければ病院テンプレート | 病院テンプレート | Table A.1-1（Enterprise Identity Option のとき） |
| Station Name | (0008,1010) | テンプレートの値 | 同じ | — |
| Series Instance UID・Frame of Reference UID | (0020,000E)・(0020,0052) | Series Instance UID はシリーズごとに作る。Frame of Reference UID は既存の生成のとおり検査ごとに1つ作る | 同じ | RAD TF-2 4.8.4.1.1.1 |
| Source Application Entity Title（File Meta） | (0002,0016) | 自分の AE タイトル | 同じ | PS3.10 |

Scheduled Station AE Title (0040,0001) は画像に写す属性ではない。取得の条件に
使い、予約の値が自分の AE タイトルと違えば、撮影の画面で「この予約は別の装置の
予定です」と出して確かめを求める。

### 6.3 決まりの補足

- **Study Instance UID は予約から写す**
  （[ADR-0017](../decisions/0017-copy-study-instance-uid-from-worklist.md)）。
  予約に無いときは作り、撮影の画面に「予約に Study Instance UID が無いため、
  このツールが作りました」と出す
- **生年月日・性別が空の予約も撮れる。** どちらもワークリストでは Type 2 で、
  空で返りうる（PS3.4 Table K.6-1）。空なら画像にも空で写し（Type 2）、
  Patient's Age は出さない。撮影の画面に「生年月日が空です」と出す。既存の
  `Patient` のモデル（[03_data_models.md](03_data_models.md)。生年月日 8 桁・
  性別 M/F/O が必須）は変えず、予約から作る経路では空を許す別のモデル
  （`ScheduledPatient`）を使う。生成の設定へ渡すところは 03 に書いてある
- 異常のデータ（`abnormal`）は、写した値にも当たる。異常のレベルを上げると、
  写した値が壊れることがある。画面の「異常のデータ」にその旨を出す
- 同じ予約で2回撮ると、同じ Study に新しいシリーズを足す（Study Instance UID は
  同じ、Series は新しく作る。RAD TF-2 4.8.4.1.1.1 の「終わった手順にシリーズを
  足さない」に従う）。予約に Study Instance UID が無く DTG が作ったときは、作った
  UID を予約の鍵ごとに状態の置き場の SQLite に覚え、2回目も同じ UID を使う

### 6.4 MPPS に写す値

N-CREATE（状態 `IN PROGRESS`）で送る主な値：Scheduled Step Attributes
Sequence（Study Instance UID・Referenced Study Sequence・Accession Number・
Requested Procedure ID・Requested Procedure Description・Scheduled Procedure
Step ID・Scheduled Procedure Step Description・Scheduled Protocol Code
Sequence）、患者の値、Performed Procedure Step ID・Start Date・Start Time・
Description、Modality、Performed Station AE Title（自分の AE タイトル）。

N-SET（状態 `COMPLETED`・`DISCONTINUED`）で Performed Series Sequence
（シリーズごとの Series Instance UID と、作った画像の SOP Class・Instance UID）と
End Date・Time を送る。Performed Series Sequence はこの時点で空にしない
（PS3.4 F.7.2 の表 F.7.2-1 の Note 2）。画像が 1 枚も無ければ、画像の無い
シリーズの項目を 1 つ入れる（Series Instance UID は新しく作り、Protocol Name は
`DTG`）。予約なしの形では Referenced Study Sequence を空にする
（RAD TF-2x Table A.1-2）。

**MPPS そのものの** SOP Class・Instance UID は DIMSE のコマンドの欄（N-CREATE の
Affected SOP Class・Instance UID、N-SET の Requested SOP Class・Instance UID）で
送り、データセットの一番上に SOP Class UID (0008,0016)・SOP Instance UID
(0008,0018) を置かない（IHE-A.1.4・A.1.5）。画像を指す Referenced SOP Class UID
(0008,1150)・Referenced SOP Instance UID (0008,1155)（Performed Series
Sequence の中）は入れる。

### 6.5 予約の値は信用しない

**ワークリストの応答の値（Patient ID・受付番号・UID・氏名など）は、相手の SCP が
自由に入れられる、信用できない値として扱う。** 画像の属性には写すが、ファイル・
フォルダの名前にはそのまま使わない。

- 名前に使うときは `[A-Za-z0-9._-]` 以外の字を `_` に置き換え、長さを 64 字まで
  にし、空・`.`・`..` などの点だけの名前は決まった名前（例：`emergency`・
  `UNKNOWN`）にし、Windows の予約名（`CON`・`NUL`・`COM1` など）は先頭に `_` を
  足す（`app/core/path_safety.py`）
- 組み立てたパスは `resolve()` して、出力の根のフォルダの中にあることを
  確かめる。外なら書かずに止める（`FileWriteError`。終了コード 3）
- Job YAML の Patient ID から作るファイルの名前（既存の生成）も同じ決まりで作る
- 撮る前に、写す値の形を確かめる。外れたら撮らずに `WorklistMappingError`
  （終了コード 4）で止める
  - Patient ID は空でなく 16 字まで（spec/03 の `Patient`・`ScheduledPatient`
    と同じ制約。LO の 64 字ではない）
  - Patient's Weight・Patient's Size は空か DS（PS3.5 の Decimal String：
    16 字まで、`+`・`-` の付いてよい10進の数、指数も可）
  - Study Instance UID は空か UID の形（`^[0-9]+(\.[0-9]+)*$`・64 字まで・
    各成分は `0` か、`0` で始まらない数字の並び。PS3.5 9.1）

---

## 7. 文字コード

### 7.1 決まり

**画像の文字コードは、既定ではワークリストの応答に合わせる（`auto`）。**
設定と撮影の画面で、次の4つから選び直せる。

| 選択 | 画像の Specific Character Set | 用途 |
|------|-------------------------------|------|
| `auto`（既定） | ワークリストの応答と同じ値。応答に無いとき・予約なしのときは `character_set_fallback`（既定 `utf8`） | 本物のモダリティの多くの動き |
| `utf8` | `ISO_IR 192` | UTF-8 の PACS |
| `jis` | `\ISO 2022 IR 87`（値 1 は空＝ISO 2022 IR 6） | 漢字を JIS で |
| `jis_kana` | `ISO 2022 IR 13\ISO 2022 IR 87` | 半角カナ＋漢字（日本の装置に多い組） |

- `character_set_fallback` には `auto` を選べない（`utf8`・`jis`・`jis_kana` の
  どれか）。これで `auto` の行き先が必ず1つに決まる
- 値 1 が空の複数の値は、値 1 を ISO 2022 IR 6 とみなす（PS3.3 C.12.1.1.2）。
  既存の病院テンプレートの `ISO 2022 IR 6\ISO 2022 IR 87` も `jis` と同じ意味で
  受け付ける
- 画面の上の帯に、取得したワークリストの文字コードと、画像に使う文字コードを
  並べて出す（例：「ワークリスト：ISO_IR 192 → 画像：ISO 2022 IR 13\ISO 2022
  IR 87」）

### 7.2 写せない字

**選んだ文字コードで表せない字があれば、黙って消さずに撮影を止める**
（[ADR-0018](../decisions/0018-stop-on-unrepresentable-characters.md)）。
どの属性のどの字かを、画面と CLI の標準エラーに出す。例：UTF-8 の予約にある、
JIS X 0208 に無い字。

- 確かめるのは画像のすべての文字の属性（予約から写した値とテンプレートの値）。
  止めるのは書き出す前で、ファイルは残さない。撮影のために作った出力のフォルダが
  空のまま残るなら、それも消す
- ISO 2022 IR 13 で受ける字（ASCII のほか）は半角カナ（JIS X 0201 の 0xA1〜
  0xDF）だけにする。`¥`・`‾` は IR 13 では 0x5C・0x7E になり、読み戻すと `\`
  （値の区切り）・`~` に化けるため、表せない字として止める。確かめは
  pydicom.charset で書いて読み戻し、元の字に戻るかで行う
- PN の漢字・かなの成分は、`jis`・`jis_kana` では ISO 2022 IR 87 の
  エスケープシーケンスで書く。`jis_kana` の英字の成分の半角カナは IR 13 で書く
- pydicom の版によって、ISO 2022 IR 13 と IR 87 の組の書き出しの動きが違いうる。
  4つの選択それぞれの書き出しと読み戻しを試験で確かめる
  （[development.md](../development.md) の 4 章）

---

## 8. 送信

### 8.1 送り先

- 送り先は設定で複数持つ（名前・AE タイトル・ホスト・ポート）
- 1つを既定の送り先にする。撮影の画面の「撮影して送る」は既定の送り先へ送る
- C-ECHO で疎通を確かめられる（PACS の画面のボタン、CLI の `echo`）

### 8.2 送信キュー

| 状態（画面の表示） | 意味 | 次の操作 |
|--------------------|------|----------|
| 待機中 | 作ったが、まだ送っていない | 送る |
| 送信中 | Association を張って送っている | — |
| 送信完了 | C-STORE の応答が Success（0x0000）か Warning（0xB000 など） | 保管確認を求める |
| 送信失敗 | Association を張れない、相手が Failure を返した、時間切れ | 再送 |

- 1回の送信では、1つの検査の画像を1つの Association で送る
- Presentation Context は SOP Class ごとに 1 つ申し込み、Transfer Syntax は
  ファイルの形と Implicit VR Little Endian を並べる（申し込む Abstract Syntax
  ごとに Implicit VR Little Endian を含める。PS3.5 10.1）。相手が Implicit を
  選べば、pynetdicom が Explicit VR Little Endian のファイルを Implicit に直して
  送る
- 失敗の理由（相手の Status の値・pynetdicom の例外の型）を残す
- 再送は失敗の分だけを送る。自動の再送は既定でしない（設定
  `retry.max_attempts` で回数を決めたときだけ）
- 送信キューと送った履歴は、状態の置き場の SQLite（標準ライブラリの `sqlite3`）
  に残す。新しい外部のパッケージは足さない
- 画像のファイルは出力のフォルダに残す（送れても消さない）。消すのは利用者の
  操作だけ
- **送る前に、各ファイルを確かめる**：シンボリックリンクは断り、ファイルを
  `resolve()` して、送るフォルダの中の普通のファイルであることを確かめる。
  外れたら1枚も送らない（`FileReadError`。最初の送信はキューに入れる前に止め、
  再送はその件を失敗にして理由を残す）。最初の送信と再送の両方で確かめる
  （キューに入れた後にファイルが替えられても送らない）
- 送信中にするのは、待機中・送信失敗の件だけ（条件つきの更新で、変わった行が
  無ければ止める）。同じ件を2つの手順が同時に送らない
- 送信中のまま 30 分より長く変わらない件は、送る手順が途中で落ちたとみなす
  （止まった送信中）。`queue list` に出し、`queue retry --stale` で失敗に
  戻してから送り直す
- 送っている間は、1ファイルを送るたびに時刻を進める（長い送信を止まったと
  みなさない）。送信中にするたびに、送る権利を表すトークンを作り、時刻を進める・
  結果と失敗を残すのはトークンが合うときだけにする。トークンが合わない
  （止まったとみなされて引き取られた）手順は、残りを送らずに止まる

### 8.3 保管確認

1. 送信完了の画像の SOP Class UID・SOP Instance UID の組を集め、
   N-ACTION（Action Type 1）で送り先に問い合わせる
2. 結果の N-EVENT-REPORT を、同じ Association か、DTG の待ち受け
   （別の Association）で受ける
3. Event Type 1（すべて成功）なら「確認済」、2（一部失敗）なら失敗した画像
   だけを「確認の失敗」にする
4. 決めた時間（既定 10 分）に結果が来なければ「確認の時間切れ」

- 送り先ごとに保管確認を使うかを選ぶ（既定は使わない）
- 待ち受けは、保管確認を使う送り先が1つでもあるときだけ立てる

#### 8.3.1 結果を受ける経路

**結果は、どちらの経路で来ても受ける。既定は別の Association（待ち受け）で
受け、N-ACTION の Association はすぐに離す**
（[ADR-0019](../decisions/0019-storage-commitment-result-path.md)）。
例外は1つ：送り先の設定 `commitment_wait_seconds` に秒を入れたときだけ、
N-ACTION の後にその秒まで同じ Association を開けたまま待ち、そこで来た
N-EVENT-REPORT も受ける。

- どちらの経路でも、受け取りの処理（8.3.2）は同じ1つを通す
- 待ち受けは `modality.listen`（既定 `127.0.0.1:11113`）で立てる。受ける
  SOP Class は Storage Commitment Push Model と Verification（相手からの疎通
  確認）だけ。呼ばれる AE タイトルが自分の AE タイトルと違う Association は断る。
  相手が SCP の役を求める SCP/SCU Role Selection は受ける
- 別の経路で受けるときは、相手が Orthanc なら `DicomModalities` に DTG を登録して
  おく必要がある（4.2・10.7）

#### 8.3.2 受け取りの決まり（相手から来る値は信用しない）

- 結果の Transaction UID が、DTG が出して**まだ待っている**か時間切れにした要求の
  UID と合うときだけ受ける。合わない・UID の形でない・Event Information が無い・
  読めないときは何も書かずに Failure を返す（Event Type が 1・2 でなければ
  `0x0113`、ほかは `0x0110`）
- 別の経路で来たときは、呼んできた AE タイトルがその要求の送り先の AE タイトルと
  同じときだけ受ける（違えば `0x0110`）
- **読む順と大きさの上限**：Event Information の大きさが 1 MiB を超えれば、
  読まずに `0x0110` を返す。読むときは先に Event Type・Transaction UID と
  呼んできた AE だけを確かめ、合ったときだけ参照の並びを読む。参照の件数
  （Referenced SOP Sequence と Failed SOP Sequence の合計）が、その要求で問い
  合わせた画像の数を超えれば、何も書かずに `0x0110` を返す。1 MiB は、1回の
  撮影の上限（2000 枚）の参照を十分に入れられる大きさ。pynetdicom が組み立てる
  前の大きさは、DTG では抑えない（待ち受けは既定でループバックだけ）
- 要求に入れた画像の組（SOP Class UID と SOP Instance UID）だけを見る。
  Referenced SOP Sequence にあれば「確認済」、Failed SOP Sequence にあれば
  「確認の失敗」（Failure Reason の数を残す）。要求に無い組は捨てる（件数の上限の
  内で）。要求したのに結果のどちらにも無い組は「確認の失敗」（理由「結果に無い」）
  にする
- Event Type が 1 でも、Failed SOP Sequence があればその画像は失敗にする
  （書いてあるほうを信じる）
- 時間切れにした後に結果が来たら、その結果で置き換える（相手の最後の答えの
  ほうが確か）。記録に「遅れて来た」と残す
- 相手から来た値は、記録に `%r` で出す。画面には件数と状態の言葉だけを出し、
  相手の文は出さない（Failure Reason は `0x0112` のような数だけ）
- 状態の確かめと書き込みは1つのトランザクションで行い、待っている（か
  時間切れの）要求にだけ書く。同じ要求に2つの結果が来たら、先に書いたほうを
  残し、後のほうには `0x0110` を返す。N-ACTION の失敗も、待っている要求だけを
  「確認の失敗」にする（先に届いた結果を上書きしない）

#### 8.3.3 いつ求めるか・キューの状態

- Web 画面では、保管確認を使う送り先へ1件が送信完了になったら、すぐに
  N-ACTION を送る（再送で送れたときも同じ）。画面のプロセスが待ち受けを立てて
  結果を受ける
- CLI では自動で求めない。`commit --job ID` で求め、待ち受けを立てて結果か
  時間切れまで待つ（11.8）。画面が同じ待ち受けのポートで動いていれば、CLI は
  待ち受けを立てられないので、その旨を出して止まる
- 求めるのは状態が送信完了の件だけ。送れた画像（Success・Warning）の組を、
  送ったときに残した SOP Class UID・SOP Instance UID から集める（ファイルは
  読み直さない）
- キューの各件に、最後の要求の状態を持たせる：「確認待ち・確認済・確認の失敗・
  確認の時間切れ」。保管確認を使わない送り先の件は「—」
- N-ACTION を送れない（Association を張れない・相手が Failure を返した）ときは
  「確認の失敗」にし、理由を残す。自動では求め直さない（`commit --job ID` で
  求め直す。新しい Transaction UID を作る）
- 時間切れ（送り先の `commitment_timeout_seconds`、既定 600 秒）は、キューを
  読むたびに確かめて「確認の時間切れ」にする
- 撮影に使った装置のプロファイルが `services.storage_commitment: false` なら、
  その撮影の件には求めない（spec/13 の 8）。撮影の出力のフォルダとプロファイルの
  名前の組を状態の置き場に残して見分ける

### 8.4 MPPS

- ワークリストの相手（または別の MPPS の相手）ごとに、MPPS を使うかを選ぶ。
  既定は使わない（4.2 のとおり Orthanc は受けない）
- 撮影の開始で N-CREATE（IN PROGRESS）、作り終わりで N-SET（COMPLETED）。
  撮影が止まったら N-SET（DISCONTINUED）
- MPPS が失敗しても撮影と送信は止めない。失敗は画面と記録に出す

#### 8.4.1 送り先・送るとき・再送

**MPPS は、ワークリストの相手の `use_mpps: true` のときだけ送り、送り先は
`modality.mpps:` の相手（書いていなければワークリストの相手）にする**
（[ADR-0020](../decisions/0020-mpps-optional-with-retry-queue.md)）。
例外は2つ：CLI の `exam --mpps`・`--no-mpps` はその撮影だけ設定を上書きする。
装置のプロファイルが `services.mpps: false` なら、設定で選んでいても送らない
（spec/13 の 8）。

- 撮影の開始は、撮影の値を確かめ終わり、画像を作り始める直前（N-CREATE）。
  作り終わりは画像を書き終えた直後（N-SET COMPLETED）
- 撮影が止まったとき（N-CREATE を送った後、画像を作る途中の誤り・表せない字
  など）は、N-SET（DISCONTINUED）を送る。画面と CLI には、撮影を取り消す操作は
  無い
- 予約に Study Instance UID が無いときは、N-CREATE より前に DTG が UID を作り、
  その UID で画像も作る（MPPS と画像の Study をそろえる）
- MPPS の SOP Instance UID も N-CREATE で決まるので、画像の Referenced Performed
  Procedure Step Sequence にその UID を入れる（6.2 の表。IHE RAD TF-2x A.1.3・
  A.2.2）
- 送る値は 6.4 のとおり。Performed Series Sequence は作った画像のヘッダーから
  組む（シリーズごとに Series Instance UID・Series Description・Protocol Name と、
  画像の Referenced SOP Class・Instance UID）
- DISCONTINUED では、止まる前に書けた画像も通知する（PS3.4 F.7.2.2.2）。読めない
  画像は飛ばす。COMPLETED で画像を読めなければ DISCONTINUED にする
- 送れない（Association を張れない・相手が Failure を返した・時間切れ）ときは、
  その通知を状態の置き場の MPPS のキューに「失敗」で残す。相手の Warning は
  送れた扱いにする
- 再送は `retry.max_attempts`（送信と同じ）の回数だけすぐに試し、それでも
  だめなら残す。残った分は CLI の `mpps retry` で送り直す（11.9）。順は必ず
  N-CREATE が先で、N-CREATE が送れていない件の N-SET は送らずに待つ
- **送れたとみなすのは、相手が Success か Warning を返したときだけ。例外は
  2つで、どちらも「前に同じ通知を送り、応答が来なかった」と記録から言える
  ときに限る**：
  1. N-CREATE に `0x0111`（同じ SOP Instance が既にある）が返り、前の
     N-CREATE が「応答なし」で終わっていた
  2. 終わりの N-SET に `0x0110`（終わった MPPS は更新できない。PS3.4
     F.7.2.2）が返り、前の同じ N-SET が「応答なし」で終わっていた
  - 前に相手が Failure を返していた・前に送っていない（N-CREATE を待って保留
    していた N-SET の初回）なら、届いていたとは言えないので失敗のまま残す
  - 「応答なし」は、Association を張って要求を送った後に、応答が来ないまま
    時間切れ・切断になったこと。Association を張れなかった・相手が Failure を
    返した・Presentation Context を断られたは「応答なし」に数えない
  - キューの行に、操作ごと（N-CREATE・N-SET）に「応答なしで終わった」印を
    残す（すぐに送り直す2回目以降も、この印で決める）
- 送り直しは、設定の `use_mpps` が false でも、キューに送れていない通知があれば
  行う（`exam --mpps` で作った分）
- **送り先は行に固定する**：N-CREATE を作るときの MPPS の相手の AE タイトル・
  ホスト・ポートを行に残し、送り直しも必ずその相手へ送る。設定を後で変えても、
  新しい相手には送らない。時間切れの秒は今の設定の値を使う
- **同じ行を2つの手順が同時に送らない**：送る前に、行の送る権利を条件つきの
  更新で取る（権利が空か、取ってから 10 分より長く経った行だけ）。取れた手順
  だけが送り、終わったら権利を外す。取れなかった行は、その回は送らずに残す
  （`mpps retry` の結果では送れていない件に数える）。画面の撮影・複数の CLI の
  間で効く
- 画像を書けなかった（OSError）・作った画像のヘッダーを読めないときも、
  N-CREATE を送っていれば DISCONTINUED を残す（開いたままにしない）
- MPPS の SOP Instance UID は DTG が作る（2.25 の UUID の形）

#### 8.4.2 ローカルで試す相手

**保管確認の SCP と MPPS の SCP は、試験の中のスタブ（`tests/modality_peers.py`）
だけで作る。DTG の機能として受ける側を持たない**
（[ADR-0021](../decisions/0021-test-only-commitment-and-mpps-peers.md)）。
例外は無い。

- 手で試すとき：保管確認は試験用の Orthanc を相手にする（[README](../../README.md)
  の手順）。MPPS は、MPPS を受ける試験の相手（RIS など）が要る。Orthanc は
  受けない（4.2）

---

## 9. 層と配置

### 9.1 決まり

**モダリティの通信と手順は `app/modality/` に置き、Service Layer の一部として
扱う。** UI（`app/cli/`・`app/web/`）からだけ呼ばれ、下の `app/services/` と
`app/core/` を使う。例外は2つ。

1. 予約から生成の設定への写し方（6 章）は、通信の要らない Pure な処理なので
   `app/core/worklist_mapping.py` に置く
2. 保管確認の待ち受け（N-EVENT-REPORT を受ける）は SCP の働きだが、SCU の手順の
   一部なので `app/modality/` に置く

### 9.2 依存の向き

```text
Web (app/web/) ─┐
CLI (app/cli/) ─┤→ Modality (app/modality/) → Service (app/services/)
                │                                   ↓
GUI (app/gui/) ─┴→ Service (app/services/) ──→ Core (app/core/)
```

- `app/modality/` が import する**このプロジェクトの中の**層は `app/services/`・
  `app/core/` だけ。`app/cli/`・`app/web/`・`app/gui/` を import しない。外の
  パッケージ（pynetdicom・pydicom・Pydantic・PyYAML）と標準ライブラリ
  （`sqlite3` など）は使ってよい。通信と永続化を Core へ移さない（Core は Pure の
  まま）
- [architecture.md](../architecture.md) の層の図も同じ

### 9.3 ファイルの配置

```text
app/
├── core/
│   ├── worklist_mapping.py   # 予約 → 生成の設定（Pure）
│   ├── worklist_charset.py   # 画像の文字コードの決め方・表せない字（Pure）
│   └── models.py             # WorklistItem・ScheduledContext
├── modality/
│   ├── __init__.py
│   ├── config.py             # 自分の AE・相手・送り先（Pydantic）
│   ├── association.py        # Association を張る共通の部分
│   ├── worklist_scu.py       # C-FIND MWL
│   ├── store_scu.py          # C-STORE・C-ECHO
│   ├── commitment_scu.py     # Storage Commitment（N-ACTION・待ち受け・結果の読み取り）
│   ├── mpps_scu.py           # N-CREATE・N-SET（送る値の組み立てを含む）
│   ├── mpps_queue.py         # MPPS の通知のキュー（sqlite3）
│   ├── queue.py              # 送信キューと履歴・保管確認の要求（sqlite3）
│   └── service.py            # ModalityService（手順をまとめる）
├── web/
│   ├── __init__.py
│   ├── __main__.py           # python -m app.web
│   ├── app.py                # FastAPI のアプリ
│   ├── auth.py               # 待ち受けのアドレスと認証
│   ├── routes/               # worklist・exam・pacs・settings
│   ├── templates/            # Jinja2
│   └── static/               # 作った CSS・htmx・Lucide の SVG
└── cli/
    ├── main.py               # サブコマンドの引数
    └── modality_commands.py  # worklist・exam・send・echo・queue・commit・mpps
```

この図は、モダリティエミュレーターのファイルだけを示す（`app/core/` のほかの
モジュールは spec/02、`app/web/` の細部は 12a）。

### 9.4 Service Layer との関係

- `StudyGeneratorService.generate` は、外から Study Instance UID と予約の値
  （`ScheduledContext`）を受け取れる。渡さなければ、Job からの生成と同じ動き
- 既存の `GenerationConfig` の制約（Patient ID 16 文字・Accession Number
  16 文字など）は予約の値にも当てる。予約の値が制約を超えたら撮影の画面で止め、
  どの値かを出す

### 9.5 例外

[08_error_handling.md](08_error_handling.md) の階層に、次がある。

```text
DICOMGeneratorError
└── ModalityError
    ├── ModalityConfigError      # 設定の誤り（ConfigurationError とは別系統）
    ├── AssociationError         # Association を張れない・断られた
    ├── WorklistQueryError       # C-FIND の失敗・時間切れ
    ├── WorklistMappingError     # 予約の値が写せない（文字・長さ）
    ├── StoreError               # C-STORE の失敗
    ├── StorageCommitmentError   # 保管確認の失敗・時間切れ
    └── MPPSError                # N-CREATE・N-SET の失敗
```

---

## 12. 設定

`config/app_config.yaml` の `modality:` と `web:` の節に書く。既定のポートは、
保管確認の待ち受けが 11113、Web 画面が 8080。

```yaml
modality:
  ae_title: "DTG_CT01"
  station_name: "DTG_CT01"
  listen:                       # 保管確認の結果を受ける待ち受け
    bind_address: "127.0.0.1"
    port: 11113
  state_dir: "modality_state"   # 予約の最後の結果・送信キュー（sqlite3）
  output_dir: "output/modality"
  character_set: "auto"         # auto, utf8, jis, jis_kana
  character_set_fallback: "utf8"  # utf8, jis, jis_kana（auto は不可）
  default_template: "ct_generic"
  default_profile: null         # 装置のプロファイル（spec/13）。null は重ねない
  default_hospital: null        # 病院テンプレート（null で使わない）
  default_pixel_mode: "ct_realistic"  # simple_text, ct_realistic
  worklist:
    ae_title: "RIS_TEST"
    host: "127.0.0.1"
    port: 4242
    timeout_seconds: 30
    query_character_set: "ISO_IR 192"  # 条件に ASCII でない字があるとき
    max_results: 1000             # 応答の上限（5.5）
    max_item_bytes: 262144
    max_total_bytes: 16777216
    use_mpps: false               # MPPS を送るか（8.4.1）
  mpps: null                      # MPPS の送り先。null はワークリストの相手
  #  ae_title: "MPPS_TEST"        # 書くときは ae_title・host・port・timeout_seconds
  #  host: "127.0.0.1"
  #  port: 4243
  #  timeout_seconds: 30
  destinations:
    - name: "PACS_TEST"
      ae_title: "PACS_TEST"
      host: "127.0.0.1"
      port: 4242
      storage_commitment: false
      commitment_timeout_seconds: 600  # 保管確認の結果を待つ秒（8.3）
      commitment_wait_seconds: 0  # 同じ Association で結果を待つ秒。0 は待たない（8.3.1）
      timeout_seconds: 30         # C-ECHO・C-STORE・N-ACTION の時間切れ
  default_destination: "PACS_TEST"
  retry:
    max_attempts: 0             # 0 = 自動で再送しない
  max_images_per_exam: 2000     # 1回の撮影の合計の画像数の上限（10.5）
web:
  bind_address: "127.0.0.1"
  port: 8080
```

- 画面は `python -m app.web`（`--config PATH`。既定は `config/app_config.yaml`）で
  起動する。`web:` の節が無ければ上の既定を使う
- ループバック以外のアドレスで待ち受けるときの認証は 10.9（パスワードは設定の
  ファイルに書かず、`DTG_WEB_PASSWORD_FILE` が指すファイルから読む）
- 読み込みは `app/modality/config.py`（Pydantic）。Core からは読まない
- AE タイトルは 16 文字以内で、空白だけのものは禁じる（PS3.5 の AE の VR）
- 例はループバックのアドレスと例の名前だけにする。施設の名前・アドレスを書かない
- 設定・状態の置き場のファイル（`worklist_last.json` など）が検証で外れたとき、
  誤りの文は「項目の名前: 原因」だけにし、入っていた値を出さない（壊れた保存の
  データに患者の氏名が入りうるため。画面・CLI・ログとも同じ）
- 項目の範囲：`commitment_timeout_seconds` は 1〜86400、`commitment_wait_seconds`
  は 0〜60（同じ Association で長く待たせない）。`mpps:` の AE タイトル・ポートは
  送り先と同じ決まり
- 待ち受け（`listen.bind_address`）の既定は `127.0.0.1`。ほかのホストから受ける
  ときだけ設定で変える。待ち受けが起動しただけで、どこからでも Association を
  受けることにならないようにするため

---

## 13. ログ

[09_logging.md](09_logging.md) に従う。

- 通信の開始・終わり・相手の Status の値・件数を INFO で残す
- 患者の氏名・生年月日はログに出さない（[development.md](../development.md) の
  3.4）。出すのは予約の鍵・受付番号・SOP Instance UID まで
- pynetdicom のログは WARNING 以上だけを通す（既定）。`--verbose` で DEBUG に
  する

---

## 14. 既知の制約

### 14.1 Orthanc の Worklists のプラグインと文字コード

`orthancteam/orthanc` の Docker イメージ 26.9.1、Worklists のプラグイン 0.9.2 で、
REST でワークリストを作り、C-FIND MWL（pynetdicom）で取得した結果（2026-10-18 に
測った）。

| 作るときの SpecificCharacterSet | 作れたか | 保存された値 | C-FIND の応答 |
|----------------------------------|----------|--------------|---------------|
| 指定なし（プラグインが ISO_IR 192 にする） | 作れた | 漢字・かな・英字ともそのまま | ISO_IR 192 で返り、読み戻した字は合っていた（生のバイト列は確かめていない） |
| `ISO 2022 IR 87` | 作れた | **氏名の漢字・かなが消えた**（エラーにならない）。検査の記述も一部だけ残った | 消えたまま返る |
| `ISO 2022 IR 13\ISO 2022 IR 87` | **作れない**（400 `Unknown encoding while creating DICOM from JSON`） | — | — |

DTG への影響：

- Orthanc の Worklists を相手にするとき、予約は UTF-8 で作る。DTG は `auto` で
  UTF-8 の画像を作る。JIS の画像が要る試験では、撮影の画面か `--charset` で
  `jis`・`jis_kana` を選ぶ
- ワークリストの値が既に消えていても、DTG は気づけない（応答は正しい形で来る）。
  漢字・かなの成分が空の予約を取得したときは、一覧に「漢字・かなが空」の印を出す

### 14.2 Orthanc の文字コードのそのほかの点

公開の資料から。

- Orthanc は C-FIND の応答（ワークリストを含む）の文字コードに
  `DefaultEncoding` の設定を使う（Orthanc の設定の見本 `Configuration.json` の注）
- C-FIND の応答で SpecificCharacterSet の複数の値を扱えるようになったのは
  1.12.2（Orthanc の `NEWS`）
- ISO_IR 13 のときの円記号（0x5C）と値の区切り `\` の扱いは 1.12.9 で直った
  （同じ `NEWS`）

### 14.3 DTG の制約

- MPPS は Orthanc を相手に使えない（4.2）
- ワークリストの SCP（RIS の役）は持たない。試験の中だけで立てる
- 画像を受信して保存する Storage SCP は持たない
  （[ADR-0013](../decisions/0013-remove-storage-scp.md)）。保管確認の SCP・
  MPPS の SCP も持たず、試験の中だけで立てる（8.4.2）。ローカルで画像を
  受けたいときは、試験用の PACS（Orthanc など）を使う
- CLI の `commit` と画面は、同じ待ち受けのポートを同時に使えない（8.3.3）
- 保管確認の時間切れは、キューを読んだときに決める。画面も CLI も動いていない
  間は「確認待ち」のまま残る
- 異常のデータで UID を壊した画像は、壊れた UID のまま N-ACTION・Performed
  Series Sequence に入れる（相手の断り方を試すのに使える）

---

## 15. 出典

2026-10-18 に読んだもの。

- DICOM PS3.4 2026d K.6.1「Modality Worklist SOP Class」
  （Table K.6-1、K.6.1.3.1 SCU Conformance）
- DICOM PS3.4 2026d C.2.2.2（Specific Character Set の扱い）
- DICOM PS3.17 2026d DD.1「Examples For The Usage of The Modality Worklist」
- DICOM PS3.17 2026d Annex B（Modality Worklist と MPPS の流れの図）
- DICOM PS3.3 C.12.1.1.2（Specific Character Set）、10.6
  （Request Attributes Macro）
- IHE Radiology TF-2 Rev. 23.0（2025-08-08）：4.5「Query Modality Worklist
  [RAD-5]」（Table 4.5-1・4.5-2・4.5-3、4.5.4.1.2.1 の Note）、4.8「Modality
  Images Stored [RAD-8]」（4.8.1、4.8.4.1.1.1、4.8.4.1.2）
- IHE Radiology TF-2x Rev. 23.0（2025-08-08）：Appendix A、Table A.1-1
  （Simple Case）・A.1-2（Unscheduled Case）、注 IHE-A.1.1〜A.1.5
- Orthanc：DICOM Conformance Summary
  （`OrthancServer/Resources/DicomConformance.txt`）、
  `OrthancFramework/Sources/DicomNetworking/Internals/CommandDispatcher.cpp`、
  `OrthancServer/Resources/Configuration.json`、`NEWS`
  （いずれも GitHub の OrthancMirror の 2026-10-09 の版）
- Orthanc Book：「DICOM storage commitment」「Worklists plugin」
  （新しいもの・古いもの）
- pynetdicom（GitHub の main。最新のリリース v3.0.4）：
  `sop_class.py`・`association.py`・`events.py`
- Tailwind CSS の GitHub releases（v4.3.3 の standalone の実行ファイル）、
  Lucide の LICENSE（ISC）
