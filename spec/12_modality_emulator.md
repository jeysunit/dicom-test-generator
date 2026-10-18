# 12. モダリティのダミー（Modality Emulator）仕様

## 要約

この道具は、本物のモダリティと同じ順で動く。ワークリストを引き
（C-FIND MWL の SCU）、予約の値を写した画像を作り、PACS へ送る
（C-STORE の SCU）。例外は3つある。

1. 予約なしの「緊急の患者」は、値を手で入れ、IHE の予約なしの形に従う
2. 保管の確認（Storage Commitment の SCU）は選べる形にする
3. MPPS（N-CREATE・N-SET の SCU）は、相手が受けるときだけ使う

画面はウェブの画面（Python の側で描く。FastAPI・Jinja2・HTMX・
Tailwind CSS）で作る。明るい地を既定にし、暗い地にも切り替えられる。
見た目の値は tsunagi-dicom とそろえ、画面はすっきりさせる（10 章の
冒頭）。
同じ操作を CLI でも行え、自動の試験から使える。

**状態**: 承認済み（2026-10-18。決まったことは「18. 決まったこと」）。
Phase 3a（CLI）・3b（ウェブの画面）を実装した。3c は未実装

**目的の線**: この道具は診療のためではなく、治験やシステムの試験の
スタブ（モダリティの役の代わり）に使う。機能は少なくてよい。

**Phase**: Phase 3a・3b・3c（「15. 段」）

**依存**: Phase 0（Core Engine）、Phase 1（Service Layer・CLI）、
Phase 1.5（Storage SCP。試験の受け手として使う）

**設計判断**: [ADR-0011](../adr/0011-modality-emulator.md)

> **Not for Diagnostic Use / 非医療機器。** 生成する画素は合成で、
> 臨床に使えない。本番の PACS への投入は対象外（00_overview の「非対象」）。
> 試験用の PACS・RIS にだけつなぐ。

---

## 1. 目的と範囲

### 目的

PACS・RIS・ビューアの試験で「モダリティの役」をこの道具に任せる。
本物の装置を使わずに、次の流れを繰り返し流せるようにする。

```text
RIS（ワークリスト）→ モダリティ → PACS
  予約を引く → 予約を選ぶ → 撮る（合成の画像）→ 送る → 確かめる
```

### 範囲に入れるもの

- C-FIND（Modality Worklist）の SCU
- C-STORE の SCU、C-ECHO の SCU
- Storage Commitment Push Model の SCU（選べる）
- MPPS（Modality Performed Procedure Step）の SCU（選べる）
- ウェブの画面（ワークリスト・撮影・PACS・設定）
- CLI（`worklist`・`exam`・`send`・`echo`・`queue`）

### 範囲に入れないもの

- ワークリストの SCP（RIS の役）。試験の中だけで pynetdicom で立てる
- Query/Retrieve（C-MOVE・C-GET）の SCU
- HL7 の受信・送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査の記録など）
- 既存の PySide6 の GUI（`spec/05_gui.md`）の作り替え。
  扱いは ADR-0011 の案 B（ウェブの画面ができたら外す。それまでは凍結）

### spec/05_gui.md との関係

- `spec/05_gui.md` は、生成の道具の PySide6 の画面（Phase 2）の仕様。
  この文書の画面とは別のもの
- モダリティの画面はこの文書で決め、ウェブの画面にする
  （ADR-0011。ADR-0003 をモダリティの画面については置き換える）
- 生成の処理（テンプレート・異常のデータ・ピクセル）は共通で、
  どちらの画面も Service Layer を通して使う

---

## 2. 用語

| 言葉 | 意味 |
|------|------|
| 予約 | ワークリストの1件（Scheduled Procedure Step） |
| ワークリストの相手 | MWL の SCP（RIS・Orthanc の Worklists など） |
| 送り先 | Storage の SCP（PACS） |
| 撮る・撮影 | 予約の値で合成の画像を作ること（この道具では生成） |
| 緊急の患者 | 予約なしで撮る患者（IHE の Unscheduled Case） |
| 保管の確認 | Storage Commitment。送った画像を相手が預かったかを問う |
| MPPS | 撮影の始まりと終わりを相手に知らせる（N-CREATE・N-SET） |
| 待ち行列 | 送る画像の列。状態は「待ち・送信中・送れた・失敗」 |

画面の言葉は医療の現場の言葉を言い換えない（tsunagi-dicom の原則 7 と
そろえる）。例：受付番号（Accession Number）、検査、シリーズ、
緊急、未送信、送信済。

---

## 3. 技師の一日（操作の流れ）

```text
1. 朝、ワークリストの画面を開く
   └ 既定の条件（今日・自分の AE タイトル）で予約を引く
2. 患者が来たら、一覧から予約を選ぶ
   └ 予約の値（氏名・ID・生年月日・受付番号など）を確かめる
   └ 必要なら「引き直し」（その予約だけを最新にする。DD.1 の4つ目の例）
3. 撮影の画面で、テンプレート・シリーズ数・枚数・異常のデータを選ぶ
   └ 予約の値は読むだけ（書き換えない）
   └ MPPS を使うなら、撮影の開始で N-CREATE（IN PROGRESS）
4. 「撮影」で画像を作り、待ち行列に入れる
   └ MPPS を使うなら、作り終わりで N-SET（COMPLETED）
5. PACS の画面で送る（自動で送る設定もできる）
   └ 送れた・失敗を見る。失敗は再送
6. 保管の確認を使うなら、結果（確認済・失敗）を見る
7. 予約なしの患者が来たら「緊急の患者」で撮る
```

---

## 4. DICOM の通信

### 4.1 この道具が持つ役割

| 役割 | SOP Class | UID | 段 | 既定 |
|------|-----------|-----|----|------|
| Verification SCU | Verification | 1.2.840.10008.1.1 | 3a | 有効 |
| MWL SCU | Modality Worklist Information Model - FIND | 1.2.840.10008.5.1.4.31 | 3a | 有効 |
| Storage SCU | テンプレートの SOP Class（例: CT Image Storage） | 1.2.840.10008.5.1.4.1.1.2 | 3a | 有効 |
| Storage Commitment SCU | Storage Commitment Push Model | 1.2.840.10008.1.20.1 | 3c | 無効 |
| MPPS SCU | Modality Performed Procedure Step | 1.2.840.10008.3.1.2.3.3 | 3c | 無効 |

- 実装は pynetdicom の `AE`・`Association` の `send_c_echo`・
  `send_c_find`・`send_c_store`・`send_n_action`・`send_n_create`・
  `send_n_set` を使う（pynetdicom の公開の API。版は requirements.txt の範囲）
- 保管の確認の結果（N-EVENT-REPORT）は、相手が**別の Association で**
  送ってくることが多い。受けるために、この道具は小さな待ち受け
  （N-EVENT-REPORT だけを受ける）を持つ。待ち受けは保管の確認を
  有効にしたときだけ立てる（「8.3 保管の確認」）

### 4.2 Orthanc の対応（2026-10-18 に公開の資料・ソースで確かめた）

| 機能 | Orthanc | 根拠 |
|------|---------|------|
| C-ECHO・C-STORE・C-FIND（MWL）の SCP | 受ける | DICOM Conformance Summary（ソースの `DicomConformance.txt`） |
| Storage Commitment の SCP | 受ける（1.6.0 から。Push Model だけ。結果は非同期で、別の Association で返す） | Orthanc Book「DICOM storage commitment」 |
| MPPS（N-CREATE・N-SET）の SCP | **受けない** | Conformance Summary に無い。`CommandDispatcher.cpp` が扱う DIMSE は C-ECHO・C-STORE・C-FIND・C-MOVE・C-GET・N-ACTION・N-EVENT-REPORT だけで、ほかは `DIMSE_BADCOMMANDTYPE` |

したがって、**MPPS は「相手が受けるときだけ」使う**。既定は無効。
Orthanc を相手にするときは無効のままにする。有効にして相手が
断ったら、撮影は止めず、MPPS の失敗として画面と記録に出す。

Orthanc の保管の確認は、要求してきたモダリティを `DicomModalities` に
登録しておく必要がある（結果を返す先の AE タイトル・住所・ポートを
Orthanc が知るため。Orthanc Book）。設定の画面に、その旨と
この道具の待ち受けの AE タイトル・ポートを出す。

---

## 5. ワークリストの引き方

### 5.1 引く条件（Matching Keys）

| 条件 | Tag | 既定 | 画面 | 出典 |
|------|-----|------|------|------|
| 予定の日（Scheduled Procedure Step Start Date） | (0040,0002) | 今日（範囲 `今日-今日` で送る） | 今日・明日・日付の指定・範囲 | RAD TF-2 Table 4.5-2 |
| モダリティ | (0008,0060) | テンプレートのモダリティ | 選ぶ・空 | 同上 |
| 予定の装置の AE タイトル（Scheduled Station AE Title） | (0040,0001) | 自分の AE タイトル | 自分・空 | 同上 |
| 患者 ID | (0010,0020) | 空 | 入力 | RAD TF-2 Table 4.5-1 |
| 患者の氏名 | (0010,0010) | 空 | 入力（各成分の末尾に `*` を足す） | 同上 |
| 受付番号 | (0008,0050) | 空 | 入力 | 同上 |
| Requested Procedure ID | (0040,1001) | 空 | 入力 | 同上 |

- 予定の日・モダリティ・AE タイトルは Scheduled Procedure Step
  Sequence (0040,0100) の中に入れる（PS3.4 K.6.1.2.2）
- 日付は範囲で送る。IHE は、単一の値の日付の一致のしかたが相手に
  よって違いうるため、範囲（`<今日>-<今日>`）を勧めている
  （RAD TF-2 4.5.4.1.2.1 の Note）
- 氏名の各成分の末尾に `*` を足す（同じ Note の勧め）。
  利用者が `*` を入れたときは足さない
- 引く条件の組は、DICOM PS3.17 DD.1 の例（日付と AE タイトル、
  日付とモダリティ、患者ごと）に合わせて画面の「すぐ選べる条件」にする

### 5.2 返してもらう値（Return Keys）

RAD TF-2 Table 4.5-3 の、SCU が R+・R+* の値をすべて求める。
主なもの：

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

- 引く条件がすべて ASCII なら、問い合わせに Specific Character Set を
  入れない（既定の文字の集まり。PS3.4 C.2.2.2）
- 氏名などに ASCII でない字があれば、設定の
  `worklist.query_character_set`（既定 `ISO_IR 192`。`jis`・`jis_kana`
  の値も選べる）で書き、その値を問い合わせの Specific Character Set に
  入れる
- 相手がその文字コードを扱わないと、一致のしかたは相手次第になる
  （PS3.4 C.2.2.2）。0 件のときは画面に「日本語の条件は相手の文字コード
  の扱いに左右されます。患者 ID か受付番号でも引いてください」と出す
- 画像の文字コードの `auto`（7 章）は、問い合わせには使わない

### 5.4 応答の扱い

- 応答の Specific Character Set を読み、値を Python の文字列に戻す
  （pydicom）。戻せない値は「読めない値」として画面に出し、
  その予約は撮影に進めない。写す Sequence の中の値（入れ子を含む）も
  確かめ、`ReferencedStudySequence>ReferencedSOPClassUID` のように
  `Sequence>属性` の形で名前を残す。Sequence の中の UID（VR が UI）は、
  UID の形（6.5）でなければ読めない値とする
- 一覧の1件ごとに、この道具の中だけで使う鍵（予約の鍵）を付ける。
  鍵は `Study Instance UID`・`Requested Procedure ID`・
  `Scheduled Procedure Step ID`・`Accession Number` をこの順に `|` で
  連ねた文字列（UTF-8）の SHA-1 の16進の先頭 10 桁。CLI の
  `--from-worklist <鍵>` で使う
- 最後に引いた結果を状態の置き場（「12. 設定」の `state_dir`）に
  保存する。CLI はこれを読む
- 相手が Pending を返し続けて決めた時間（既定 30 秒）を過ぎたら
  C-CANCEL を送り、「途中まで」として受け取った分を出す
- `exam --refresh`（その予約だけを引き直す）のときは、時間の上限で
  途中までになったら撮らずに `WorklistQueryError`（終了コード 5）で止める。
  ほかの引き方は途中までを返すまま

### 5.5 応答の上限

**相手が返す応答は、受け取りながら数え、上限を超えたら C-CANCEL を
送って Association を切り、`WorklistQueryError`（終了コード 5）で
止める。** 途中まで受け取った分は出さない。例外は1つ：時間の上限
（`timeout_seconds`）は 5.4 のとおり C-CANCEL して「途中まで」を出す。

| 上限 | 設定（`modality.worklist`） | 既定 |
|------|------------------------------|------|
| 件数 | `max_results` | 1000 |
| 1件の大きさ（Implicit VR で書いたときのバイト数） | `max_item_bytes` | 256 KiB |
| 合計の大きさ | `max_total_bytes` | 16 MiB |
| C-CANCEL の後に返し続ける時間 | `timeout_seconds` と同じ長さ | 30 秒 |

- 上限は、その件を一覧に足す前に確かめる。1件の大きさは pynetdicom が
  1件を受け取った後でしか量れない（受け取りの途中で止める口が無い）。
  1件がメモリに載る大きさは pynetdicom の受け取りに任せる
- C-CANCEL の後も相手が返し続けたら、待つのは `timeout_seconds` の分
  だけにし、Association を切って `WorklistQueryError` にする

---

## 6. 予約から画像への値の写し方

### 6.1 決まり

**予約にある値は、そのまま写す。** 予約に無い値は、この道具が作るか
空にする。出典は IHE RAD TF-2x Appendix A の Table A.1-1（予約どおりの
形）と Table A.1-2（予約なしの形）。IHE は、モダリティが予約の値を
画像の頭に入れることを求める（RAD TF-2 4.8.1・4.8.4.1.2）。

### 6.2 表

「写す」は予約の値をそのまま使う。「作る」はこの道具が作る。

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
| Study Instance UID | (0020,000D) | **予約にあれば写す。無ければ作る**（2.25） | 作る | RAD TF-2x Table A.1-1・A.1-2、RAD TF-2 4.8.4.1.1.1 |
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

Scheduled Station AE Title (0040,0001) は画像に写す属性ではない。
引く条件に使い、予約の値が自分の AE タイトルと違えば、撮影の画面で
「この予約は別の装置の予定です」と出して確かめを求める。

### 6.3 決まりの補足

- **Study Instance UID を予約から写すことを既定にする。** IHE は、
  Study Instance UID を Order Filler が作ってワークリストで渡すことを
  基本とし、モダリティが作るのは予約なしの形などに限っている
  （RAD TF-2 4.8.4.1.1.1）。Orthanc の Worklists のプラグインの
  「検査が届いたら予約を消す」（`DeleteWorklistsOnStableStudy`）も、
  予約の Study Instance UID と届いた検査の UID の一致で動く
  （Orthanc Book「Worklists plugin」）
- 予約に Study Instance UID が無いときは作り、撮影の画面に
  「予約に Study Instance UID が無いため、この道具が作りました」と出す
- **生年月日・性別が空の予約も撮れる。** どちらもワークリストでは
  Type 2 で、空で返りうる（PS3.4 Table K.6-1）。空なら画像にも空で
  写し（Type 2）、Patient's Age は出さない。撮影の画面に「生年月日が
  空です」と出す。既存の `Patient` のモデル（`spec/03_data_models.md`。
  生年月日 8 桁・性別 M/F/O が必須）は変えず、予約から作る道では
  空を許す別のモデル（`ScheduledPatient`）を使う。生成の設定へ渡す
  ところの変更は Phase 3a の PR で 03 に書く
- 異常のデータ（`abnormal`）は、写した値にも効く。異常のレベルを
  上げると、写した値が壊れることがある。画面の「異常のデータ」に
  その旨を出す
- 同じ予約で2回撮ると、同じ Study に新しいシリーズを足す
  （Study Instance UID は同じ、Series は新しく作る。RAD TF-2
  4.8.4.1.1.1 の「終わった手順にシリーズを足さない」に従う）。予約に
  Study Instance UID が無くこの道具が作ったときは、作った UID を予約の鍵
  ごとに状態の置き場の SQLite に覚え、2回目も同じ UID を使う

### 6.4 MPPS に写す値（Phase 3c）

N-CREATE（状態 `IN PROGRESS`）で送る主な値：Scheduled Step
Attributes Sequence（Study Instance UID・Referenced Study Sequence・
Accession Number・Requested Procedure ID・Requested Procedure
Description・Scheduled Procedure Step ID・Scheduled Procedure Step
Description・Scheduled Protocol Code Sequence）、患者の値、
Performed Procedure Step ID・Start Date・Start Time・Description、
Modality、Performed Station AE Title（自分の AE タイトル）。
N-SET（状態 `COMPLETED`）で Performed Series Sequence（シリーズごとの
Series Instance UID と、作った画像の SOP Class・Instance UID）と
End Date・Time を送る。予約なしの形では Referenced Study Sequence を
空にする（RAD TF-2x Table A.1-2）。**MPPS そのものの** SOP Class・
Instance UID は DIMSE のコマンドの欄（N-CREATE の Affected SOP
Class・Instance UID、N-SET の Requested SOP Class・Instance UID）で
送り、データセットの一番上に SOP Class UID (0008,0016)・SOP Instance
UID (0008,0018) を置かない（IHE-A.1.4・A.1.5）。画像を指す
Referenced SOP Class UID (0008,1150)・Referenced SOP Instance UID
(0008,1155)（Performed Series Sequence の中）は入れる。

### 6.5 予約の値は信用しない

**ワークリストの応答の値（Patient ID・受付番号・UID・氏名など）は、
相手の SCP が自由に入れられる信用できない値として扱う。** 画像の
属性には写すが、ファイル・フォルダの名前にはそのまま使わない。

- 名前に使うときは `[A-Za-z0-9._-]` 以外の字を `_` に置き換え、長さを
  64 字までにし、空・`.`・`..` などの点だけの名前は決まった名前
  （例：`emergency`・`UNKNOWN`）にし、Windows の予約名（`CON`・`NUL`・
  `COM1` など）は先頭に `_` を足す（`app/core/path_safety.py`）
- 組み立てたパスは `resolve()` して、出力の根のフォルダの中にあることを
  確かめる。外なら書かずに止める（`FileWriteError`。終了コード 3）
- Job YAML の Patient ID から作るファイルの名前（既存の生成）も同じ
  決まりで作る
- 撮る前に、写す値の形を確かめる。外れたら撮らずに
  `WorklistMappingError`（終了コード 4）で止める
  - Patient ID は空でなく 16 字まで（spec/03 の `Patient`・
    `ScheduledPatient` と同じ制約。LO の 64 字ではない）
  - Patient's Weight・Patient's Size は空か DS（PS3.5 の Decimal
    String：16 字まで、`+`・`-` の付いてよい10進の数、指数も可）
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

- `character_set_fallback` には `auto` を選べない（`utf8`・`jis`・
  `jis_kana` のどれか）。これで `auto` の行き先が必ず1つに決まる
- 値 1 が空の複数の値は、値 1 を ISO 2022 IR 6 とみなす
  （PS3.3 C.12.1.1.2）。既存の病院テンプレートの
  `ISO 2022 IR 6\ISO 2022 IR 87` も `jis` と同じ意味で受け付ける
- 画面の上の帯に、引いたワークリストの文字コードと、画像に使う文字
  コードを並べて出す（例：「ワークリスト：ISO_IR 192 → 画像：
  ISO 2022 IR 13\ISO 2022 IR 87」）

### 7.2 写せない字

- 選んだ文字コードで表せない字（例：UTF-8 の予約にある、JIS X 0208 に
  無い字）があれば、**黙って消さない**。撮影を止め、どの属性のどの字か
  を画面と CLI の標準エラーに出す
- 「表せない字を `?` に置き換えて撮る」は、異常のデータの一つとして
  明示して選んだときだけ行う。Phase 3a ではこの選択を作らない
  （表せない字があれば必ず止める）
- 確かめるのは画像のすべての文字の属性（予約から写した値と
  テンプレートの値）。止めるのは書き出す前で、ファイルは残さない。
  撮影のために作った出力のフォルダが空のまま残るなら、それも消す
- ISO 2022 IR 13 で受ける字（ASCII のほか）は半角カナ（JIS X 0201 の
  0xA1〜0xDF）だけにする。`¥`・`‾` は IR 13 では 0x5C・0x7E になり、
  読み戻すと `\`（値の区切り）・`~` に化けるため、表せない字として止める。
  確かめは pydicom.charset で書いて読み戻し、元の字に戻るかで行う
- PN の漢字・かなの成分は、`jis`・`jis_kana` では ISO 2022 IR 87 の
  エスケープで書く。`jis_kana` の英字の成分の半角カナは IR 13 で書く
- pydicom の版によって、ISO 2022 IR 13 と IR 87 の組の書き出しの
  動きが違いうる。Phase 3a の試験で、4つの選択それぞれの書き出しと
  読み戻しを確かめる（「14. 試験」）

---

## 8. 送信

### 8.1 送り先

- 送り先は設定で複数持つ（名前・AE タイトル・住所・ポート）
- 1つを「既定の送り先」にする。撮影の画面の「撮影して送る」は
  既定の送り先へ送る
- C-ECHO で疎通を確かめられる（PACS の画面のボタン、CLI の `echo`）

### 8.2 待ち行列

| 状態 | 意味 | 次の操作 |
|------|------|----------|
| 待ち | 作ったが、まだ送っていない | 送る・取り消す |
| 送信中 | Association を張って送っている | — |
| 送れた | C-STORE の応答が Success（0x0000）か Warning（0xB000 など） | 保管の確認を求める |
| 失敗 | Association を張れない、相手が Failure を返した、時間切れ | 再送・取り消す |

- 1回の送信では、1つの検査の画像を1つの Association で送る
- 失敗の理由（相手の Status の値・pynetdicom の例外の型）を残す
- 再送は失敗の分だけを送る。自動の再送は既定でしない
  （設定 `retry.max_attempts` で回数を決めたときだけ）
- 待ち行列と送った履歴は、状態の置き場の SQLite（標準ライブラリの
  `sqlite3`）に残す。新しい外部の包みは足さない
- 画像のファイルは出力のフォルダに残す（送れても消さない）。
  消すのは利用者の操作だけ
- 送信中にするのは、待ち・失敗の件だけ（条件つきの更新で、変わった行が
  無ければ止める）。同じ件を2つの手順が同時に送らない
- 送信中のまま 30 分より長く変わらない件は、送る手順が途中で落ちたと
  みなす（「止まった送信中」）。`queue list` に出し、
  `queue retry --stale` で失敗に戻してから送り直す
- 送っている間は、1ファイルを送るたびに時刻を進める（長い送信を
  止まったとみなさない）。送信中にするたびに送る権利の札を作り、
  時刻を進める・結果と失敗を残すのは札が合うときだけにする。札が合わない
  （止まったとみなされて引き取られた）手順は、残りを送らずに止まる

### 8.3 保管の確認（Phase 3c）

1. 送れた画像の SOP Class UID・SOP Instance UID の組を集め、
   N-ACTION（Action Type 1）で送り先に問う
2. 結果の N-EVENT-REPORT を、同じ Association か、この道具の待ち受け
   （別の Association）で受ける
3. Event Type 1（すべて成功）なら「確認済」、2（一部失敗）なら
   失敗した画像だけを「確認の失敗」にする
4. 決めた時間（既定 10 分）に結果が来なければ「確認の時間切れ」

- 送り先ごとに「保管の確認を使う」を選ぶ（既定は使わない）
- 待ち受けは保管の確認を使う送り先が1つでもあるときだけ立てる

### 8.4 MPPS（Phase 3c）

- ワークリストの相手（または別の MPPS の相手）ごとに「MPPS を使う」を
  選ぶ。既定は使わない（「4.2」のとおり Orthanc は受けない）
- 撮影の開始で N-CREATE（IN PROGRESS）、作り終わりで N-SET
  （COMPLETED）。撮影を取り消したら N-SET（DISCONTINUED）
- MPPS が失敗しても撮影と送信は止めない。失敗は画面と記録に出す

---

## 9. 層と配置

### 9.1 決まり

**モダリティの通信と手順は `app/modality/` に置き、Service Layer の
一部として扱う。** UI（`app/cli/`・`app/web/`）からだけ呼ばれ、
下の `app/services/` と `app/core/` を使う。例外は2つ。

1. 予約から生成の設定への写し方（6 章）は、通信の要らない Pure な
   処理なので `app/core/worklist_mapping.py` に置く
2. 保管の確認の待ち受け（N-EVENT-REPORT を受ける）は SCP の働きだが、
   SCU の手順の一部なので `app/modality/` に置く（`app/scp/` には
   置かない）

### 9.2 依存の向き

```text
Web (app/web/) ─┐
CLI (app/cli/) ─┤→ Modality (app/modality/) → Service (app/services/)
                │                                   ↓
GUI (app/gui/) ─┤→ Service (app/services/) ──→ Core (app/core/)
SCP (app/scp/) ─┘→ Core (app/core/)
```

- `app/modality/` が import する**このプロジェクトの中の**層は
  `app/services/`・`app/core/` だけ。`app/cli/`・`app/web/`・
  `app/gui/`・`app/scp/` を import しない。外の包み（pynetdicom・
  pydicom・Pydantic・PyYAML）と標準ライブラリ（`sqlite3` など）は
  使ってよい。通信と永続化を Core へ移さない（Core は Pure のまま）
- `app/scp/`（Storage SCP、Phase 1.5）は「受ける側」の道具で、
  `app/modality/`（送る側）とは互いに import しない。並べて使うと、
  この道具だけで「撮る→送る→受ける」を閉じた試験にできる
  （「14. 試験」）
- `WORKFLOW.md` の層の図に `app/modality/` と `app/web/` を足す
  （この PR では図は変えない。Phase 3a の PR で変える）

### 9.3 ファイルの配置（案）

```text
app/
├── core/
│   ├── worklist_mapping.py   # 予約 → 生成の設定（Pure）
│   ├── worklist_charset.py   # 画像の文字コードの決め方・表せない字（Pure）
│   └── models.py             # WorklistItem・ScheduledContext を足す
├── modality/
│   ├── __init__.py
│   ├── config.py             # 自分の AE・相手・送り先（Pydantic）
│   ├── worklist_scu.py       # C-FIND MWL
│   ├── store_scu.py          # C-STORE・C-ECHO
│   ├── commitment_scu.py     # Storage Commitment（N-ACTION・待ち受け）
│   ├── mpps_scu.py           # N-CREATE・N-SET
│   ├── queue.py              # 待ち行列と履歴（sqlite3）
│   └── service.py            # ModalityService（手順をまとめる）
├── web/
│   ├── __init__.py
│   ├── __main__.py           # python -m app.web
│   ├── app.py                # FastAPI のアプリ
│   ├── auth.py               # 待ち受けの住所と認証
│   ├── routes/               # worklist・exam・pacs・settings
│   ├── templates/            # Jinja2
│   └── static/               # 作った CSS・htmx・Lucide の SVG
└── cli/
    ├── main.py               # サブコマンドの引数を足す
    └── modality_commands.py  # worklist・exam・send・echo・queue
```

### 9.4 Service Layer の変更（Phase 3a）

- `StudyGeneratorService.generate` に、外から Study Instance UID と
  予約の値（`ScheduledContext`）を渡せる引数を足す。渡さなければ
  いまと同じ動き（既存の試験を変えない）
- 既存の `GenerationConfig` の制約（Patient ID 16 文字・Accession
  Number 16 文字など）は予約の値にも当てる。予約の値が制約を超えたら
  撮影の画面で止め、どの値かを出す

### 9.5 例外

`spec/08_error_handling.md` の階層に、次を足す（Phase 3a の PR で
08 を更新する）。

```text
DICOMGeneratorError
└── ModalityError
    ├── ModalityConfigError      # 設定の誤り（ConfigurationError とは別系統）
    ├── AssociationError         # Association を張れない・断られた
    ├── WorklistQueryError       # C-FIND の失敗・時間切れ
    ├── WorklistMappingError     # 予約の値が写せない（文字・長さ）
    ├── StoreError               # C-STORE の失敗
    ├── StorageCommitmentError   # 保管の確認の失敗・時間切れ
    └── MPPSError                # N-CREATE・N-SET の失敗
```

---

## 10. ウェブの画面

### 画面の方向（2026-10-18 に承認者が決めた）

**画面はすっきりさせる。余白を取り、部品を少なくし、一画面にやる
ことを1つにする。** クラウド型の電子カルテのような、余白の多い
静かな画面を目安にする。例外は無い。

- 理由：この道具は診療のためではなく、治験やシステムの試験の
  スタブとして使う。技師の操作の全部を写す必要は無く、試験に要る
  「引く→選ぶ→撮る→送る→確かめる」が迷わず流せればよい
- **機能を足すより削る。** 画面に何かを足したくなったら、まず
  「試験のスタブに要るか」を問う。要らなければ足さない。CLI か設定の
  ファイルでできることは、画面に出さなくてよい
- 一画面の主のボタンは1つにする（例：ワークリストは「選んで撮影へ」、
  撮影は「撮影して送る」）。ほかの操作は線か影のボタンにして控えめに
  する
- 詳しい値（予約の値の全部・UID など）は最初から並べず、開いて
  見せる（パネル・折りたたみ）
- 下の 10.3〜10.8 の部品・文字は、この方向で削ってよい。削った物は
  Phase 3b の PR で、この文書から消す

### 10.1 技術（決まった）

**画面は (a)：Python の側で描くウェブの画面（FastAPI・Jinja2・HTMX・
Tailwind CSS の standalone の実行ファイル）にする**（2026-10-18 に
承認者が決めた）。見た目の値（色・文字・部品の形）は tsunagi-dicom と
同じにする。下の表は決めたときの比較。

| 観点 | (a) FastAPI＋Jinja2＋HTMX＋Tailwind | (b) Next.js の画面＋Python の API |
|------|--------------------------------------|-----------------------------------|
| core の再利用 | Python の core・services をそのまま呼ぶ | API を挟む。型を2つの言語で持つ |
| 統一感 | 色・文字・部品の形は同じ値で作れる。React の部品そのものは使えない | tsunagi-dicom の部品を写せる |
| 保守の手間 | 1つの言語・1つの試験の道具（pytest） | Node と Python の2つの作り・2つの試験 |
| 依存の数 | Python の包み 4〜5 個（下）＋ Tailwind の standalone の実行ファイル＋ htmx の1ファイル | Node の包み（数百）＋ Python の API の包み |
| CI | pytest だけ（CSS は作った物を commit し、CI で作り直して差が無いことを確かめる） | Node と Python の2つの仕事 |
| 配布 | `python -m app.web` で起動 | 2つのプロセスかコンテナ |

- Node は要らない。Tailwind CSS v4 は standalone の実行ファイル
  （GitHub の releases に OS ごとの実行ファイルと `sha256sums.txt` が
  ある。2026-10-18 時点の最新は v4.3.3）で CSS を作れる。版を固定し、
  sha256 を確かめてから使う
- 作った CSS（`app/web/static/app.css`）は commit する。利用者は
  Tailwind の実行ファイル無しで動かせる
- htmx は1つの JavaScript のファイルを `app/web/static/` に置く
  （版を固定し、取得の元と sha256 を README に書く。外の CDN から
  読まない。手元だけで動かすため）
- アイコンは Lucide（ISC License）の SVG を、使う分だけ
  `app/web/static/icons/` に置く。ライセンスの文を同じ場所に置く
- 足す Python の包み（2026-10-18 に承認された。requirements.txt へは
  使い始める Phase 3b の PR で足す）：`fastapi`・`uvicorn`・`jinja2`・
  `python-multipart`（フォーム）、試験用に `httpx`（FastAPI の
  TestClient が使う）
- 画面の更新（待ち行列の状態など）は HTMX の定期の取得
  （`hx-trigger="every 2s"`）で行う。SSE・WebSocket は使わない

**将来の案（この PR では作らない）**：色・文字の値（design tokens。
明るい地と暗い地の両方）を1か所（例：JSON のファイル）に持ち、
tsunagi-dicom の `src/app/globals.css` の `@theme` と、この道具の
Tailwind の入力の CSS を、そこから作る。両方で同じ値を使う。それまでは、この道具の入力の CSS に
tsunagi-dicom と同じ値を書き、出典（リポジトリ・ファイル・日付）を
注に書く。値がずれたら気づけるよう、値の一覧を試験で確かめる。

### 10.2 見た目の基準（tsunagi-dicom の `docs/spec.md` 2 と同じ値）

**モダリティのダミーの画面（ワークリスト・撮影・PACS・設定）は、
明るい地を既定にし、暗い地にも切り替えられる。** 例外は1つ：画像の
サムネイルを並べる所だけ、まわりを暗い地にする。

- 理由：これらは文字を読む画面で、日本の医療機関で広く使われている
  画面でも、画像を見る画面は暗い地、一覧や事務の画面は明るい地が多い。
  tsunagi-dicom の見た目の基準（PR #9 `docs/theme-light-lists` の
  `docs/spec.md` 2）と同じ形にする
- 地の切り替えは見出しのボタンで行い、利用者の手元（ブラウザの
  `localStorage`）に覚える。覚えが無ければ明るい地
- どちらの地でも、基準の文字 14px（0.875rem）・行間 1.5。表の行・
  入力の欄も 14px を下回らない（補いの文字だけ 12px）
- 部品の間の余白は広めに取り、詰めない（10 章の冒頭の方向）：群
  （パネル）の間は 16〜24px、群の中の欄の間は 12px 以上、頁の左右は
  16px 以上。1画面に詰め込まず、詳細はパネルを開いて見せる
- 文字と地の対比は WCAG 2.2 の AA（4.5:1）以上にする

| 名前 | 明るい地（既定） | 暗い地 | 用途 |
|------|------------------|--------|------|
| `--color-background` | `#ffffff` | `#121417` | 地 |
| `--color-surface` | `#f6f8fa` | `#1a1d21` | 見出し・パネルの地 |
| `--color-foreground` | `#1f2328` | `#e6edf3` | 文字 |
| `--color-label` | `#59636e` | `#8a949e` | ラベル |
| `--color-value` | `#1f2328`（太字） | `#ffffff`（太字） | 値 |
| `--color-border` | `#d1d9e0` | `#2a2f36` | 線 |
| `--color-muted` | `#eff2f5` | `#23272d` | 行の hover・弱い地 |
| `--color-primary` | `#0969da` | `#1f6feb` | 主のボタン・フォーカスの輪 |
| `--color-primary-foreground` | `#ffffff` | `#ffffff` | 主のボタンの文字 |
| `--color-danger` | `#d1242f` | `#ff7b72` | 失敗・止める知らせの文字（Phase 3b の PR で足した） |
| `--font-sans` | `system-ui, "Noto Sans JP", sans-serif` | 同じ | 本文 |
| `--font-mono` | `ui-monospace, "Noto Sans Mono", monospace` | 同じ | UID |

- 明るい地の値は tsunagi-dicom の PR #9（2026-10-18 時点で未マージ）、
  暗い地の値は tsunagi-dicom の main の `src/app/globals.css` の
  `@theme` から写した。PR #9 の値が変わったら、この表も直す
- 対比の計算（WCAG 2.x の相対輝度の式。2026-10-18 に計算）：
  明るい地の文字 `#1f2328` は `#ffffff` に 15.8:1・`#f6f8fa` に
  14.8:1、ラベル `#59636e` は 6.1:1・5.7:1。暗い地の文字 `#e6edf3`
  は `#121417` に 15.6:1、ラベル `#8a949e` は `#1a1d21` に 5.5:1。
  いずれも AA を満たす
- 明るい地の `--color-muted` は `#eff2f5`（Phase 3b の PR で決めた）。
  その上で文字 `#1f2328` は 14.1:1、ラベル `#59636e` は 5.4:1、主の色
  `#0969da` は 4.6:1 で、どれも AA を満たす。暗い地の `#23272d` の上では
  文字 `#e6edf3` が 12.7:1、ラベル `#8a949e` が 4.9:1
- `--color-danger`（Phase 3b の PR で足した。tsunagi-dicom の表には無い）は、
  明るい地の `#d1242f` が `#ffffff` に 5.2:1・`#f6f8fa` に 4.9:1・
  `#eff2f5` に 4.7:1、暗い地の `#ff7b72` が `#121417` に 7.3:1・`#1a1d21`
  に 6.7:1・`#23272d` に 6.0:1 で、どれも AA を満たす
- **明るい地の主の色は `#0969da`**（2026-10-18 に承認者が決めた）。
  白の地との対比は 5.19:1、`#f6f8fa` の地とは 4.88:1、主のボタンの
  白の文字とは 5.19:1 で、どれも AA（4.5:1）を満たす。明るい地の控えめな地
  （`--color-surface`）は `#f6f8fa`
- **暗い地の主の色は `#1f6feb`**（2026-10-18 に承認者が決めた）。主のボタンの
  地で、白の文字との対比は 4.63:1（AA を満たす）。前の `#2f81f7` は白の文字と
  3.75:1 で届かなかったので替えた。`--color-primary-foreground` は両方の地で
  `#ffffff`。注意：`#1f6feb` は暗い地（`#121417` に 3.98:1、`#1a1d21`
  に 3.65:1）の上では、文字には使えない（AA の 4.5:1 に届かない）。
  フォーカスの輪など文字でない図形の色は 3:1 以上が目安で、満たす
- 部品の形も tsunagi-dicom の `src/components/ui/` にそろえる：
  - ボタン：高さ 32px（`h-8 px-3`）、角 `rounded-md`、文字 `text-sm`
    `font-medium`、アイコン 16px。種類は主（`bg-primary`）・線
    （`border border-border`）・影（`hover:bg-muted`）の3つ
  - 表：見出しの行は `h-9`・ラベルの色・`font-normal`、セルは
    `px-2 py-1.5`、行の線 `border-b border-border`、hover で
    `bg-muted/50`
- 字体の名前に商用の字体を書かない

### 10.3 共通の部品

- **見出し**（どの頁にも1つ）：左に道具の名前（`dicom-test-generator`、
  太字・値の色）、真ん中に頁の切り替え（ワークリスト・撮影・PACS・
  設定）、右に地の切り替え（明るい地・暗い地）と「Not for Diagnostic
  Use / 非医療機器」（Lucide の `shield-alert`、ラベルの色）。表示は tsunagi-dicom の
  `site-header` と同じ。機能ごとの断り書きは足さない
- **自分の帯**（見出しの下）：自分の AE タイトル・ワークリストの相手・
  既定の送り先・文字コード（ワークリスト → 画像）を1行で出す
- **知らせ**：操作の結果（成功・失敗）を、その操作のボタンの下に出す。
  失敗は次の操作まで消えずに残す（Phase 3b で決めた。右上に浮かべる
  知らせは作らない）
- 患者の値の出し方は tsunagi-dicom の 3.1 に合わせる：漢字の氏名は
  14px・太字・値の色、かなの氏名は 12px・ラベルの色、生年月日は
  `1975/05/10（51歳・男）` の形（和暦は Phase 3b で削った）。UID は
  0.75rem・等幅・ラベルの色で、コピーのボタンを付ける

### 10.4 ワークリストの画面

```text
┌ dicom-test-generator  [ワークリスト] 撮影  PACS  設定   ⚠ Not for Diagnostic Use / 非医療機器 ┐
│ 自分: DTG_CT01 │ ワークリスト: RIS_TEST │ 送り先: PACS_TEST │ 文字: ISO_IR 192 → ISO_IR 192 │
├──────────────────────────────────────────────────────────────────────┤
│ 予定の日 [今日 ▼]  モダリティ [CT ▼]  AE [自分 ▼]                       │
│ 患者 ID [      ]  氏名 [      ]  受付番号 [      ]   [引く] [条件を戻す] │
├──────────────────────────────────────────────────────────────────────┤
│ 時刻  患者 ID   氏名            生年月日・性別        受付番号  検査の記述 │
│ 09:00 P000001  山田 太郎        1980/01/15（45歳・男） A0001    胸部 CT   │
│              やまだ たろう                                            │
│ 09:30 P000002  …                                                      │
├──────────────────────────────────────────────────────────────────────┤
│ 12 件（14:05:31 に引いた）               [選んで撮影へ] [この予約を引き直す] │
└──────────────────────────────────────────────────────────────────────┘
```

- 行を選ぶと、一覧の下に詳細のパネル（予約の値の全部・Study Instance UID・
  Scheduled Procedure Step ID・予定の AE タイトル・文字コード）
- 予定の日は「今日・明日・日付を指定・絞らない」から選ぶ。範囲は CLI の
  `--date` で引く。モダリティの欄は空にすると絞らない。AE は「自分・
  絞らない」から選ぶ
- 図の [条件を戻す] と、Requested Procedure ID の欄は作らない（Phase 3b で
  削った。頁を開き直せば既定の条件に戻る）
- 「引き直し」は、選んだ予約を受付番号と Requested Procedure ID で
  引き直し、最新の値にする
- 予定の AE タイトルが自分と違う予約は、行に「別の装置」の印を付ける
- 0 件のとき：「予約はありません。条件を広げるか、緊急の患者で撮って
  ください」と、[緊急の患者で撮る] のボタン

### 10.5 撮影の画面

```text
┌ 予約の値（読むだけ） ───────────────────────────────────────────┐
│ 患者 ID P000001   氏名 山田^太郎=やまだ^たろう   1980/01/15・男  │
│ 受付番号 A0001   検査の記述 胸部 CT   Study UID 2.25.1234… [⧉]    │
│ 文字コード：ワークリスト ISO_IR 192 → 画像 [auto ▼]               │
├ 撮影の設定 ─────────────────────────────────────────────────────┤
│ テンプレート [ct_generic ▼]  装置 [なし ▼]  病院 [なし ▼]          │
│ シリーズ数 [2]  枚数 [1, 20]  ピクセル [CT 風 ▼]                   │
│ 異常のデータ [なし ▼]                                             │
├─────────────────────────────────────────────────────────────────┤
│ [撮影] [撮影して送る]                       MPPS: 使わない（設定）   │
└─────────────────────────────────────────────────────────────────┘
```

- 予約の値は入力の欄にしない（読むだけ）。直したいときは RIS の側で
  直して「引き直す」
- テンプレートのモダリティと予約のモダリティが違えば、[撮影] を
  押せなくし、「予約は MR、テンプレートは CT です」と出す
- 「装置」は装置のプロファイル（`spec/13_device_profiles.md`）。選べば
  テンプレートの上に重ねる。プロファイルのモダリティが予約と違うときも
  同じく止める
- 「緊急の患者」：予約なしで開いたときは、患者の値（ID・氏名の
  英字・漢字・かな・生年月日・性別）を入力の欄にする。受付番号は
  空で固定し、「予約なし（受付番号は空）」と出す
- 主のボタンは [撮影して送る]（既定の送り先へ）。[撮影] は線のボタンにし、
  撮った後の結果に [送る] を出す
- 図の「病院」「ピクセル」「MPPS」の欄と、進みのバー・取り消しは作らない
  （Phase 3b で削った）。病院とピクセルは設定の既定を使い、CLI の
  `--hospital`・`--pixel-mode` で選べる。MPPS は 3c。作る枚数は試験の
  分だけで、待たずに終わるため、進みは出さない
- 「文字コード」は撮影の設定の欄に置き、設定の既定を初めの値にする

### 10.6 PACS の画面

- **送り先の一覧**：名前・AE タイトル・住所・ポート・保管の確認の
  有無。各行に [C-ECHO] と、押した結果（つながった（○ ms）・
  つながらない（理由））
- **送信の待ち行列と送った履歴**：1つの表にまとめる（Phase 3b で決めた）。
  検査ごとの行（ID・状態・送り先・受付番号・送れた枚数／枚数・時刻・
  出力のフォルダ）。新しい件を上にする。状態は「待ち・送信中・送れた・
  失敗」。失敗の行は理由と [再送]。表の上に [失敗をすべて再送]。2 秒ごとに
  取り直す。出力のフォルダはコピーのボタンで写せる
- **保管の確認の結果**（Phase 3c）：「確認待ち・確認済・確認の失敗・
  確認の時間切れ」
- Phase 3b で削ったもの：待ちの件の [送る]・[取り消す]（画面から作る件は
  すぐ送るので待ちに残らない）、履歴の日付の絞り込み、行の患者の氏名
  （待ち行列は氏名を持たない）、送り先ごとの最後の C-ECHO の時刻（押した
  結果だけをその場に出す）

### 10.7 設定の画面

| 群 | 項目 |
|----|------|
| 自分 | AE タイトル・待ち受けのポート（保管の確認の結果を受ける）・Station Name |
| ワークリストの相手 | AE タイトル・住所・ポート・時間切れ・MPPS を使うか |
| 送り先 | 一覧（足す・直す・消す）・既定の送り先・保管の確認を使うか |
| 文字コード | 既定（`auto`・`utf8`・`jis`・`jis_kana`） |
| 撮影 | 既定のテンプレート・病院・ピクセル・出力のフォルダ |

- **設定の画面は読むだけにする**（Phase 3b で決めた。画面から書き出す
  機能は削った）。上の表の値と、読んだ設定のファイルの場所を出す。直す
  ときは設定のファイル（`config/app_config.yaml` の `modality:` の節。
  「12. 設定」）を直して、画面を起動し直す
- 設定の画面の下に「Orthanc で保管の確認を使うときは、この道具を
  Orthanc の `DicomModalities` に登録してください（AE タイトル・
  住所・待ち受けのポート）」と出す（保管の確認と同じ 3c で出す）

### 10.8 画面の文字の案

| 場所 | 文字 |
|------|------|
| 頁の名前 | ワークリスト・撮影・PACS・設定 |
| ワークリストのボタン | 引く・選んで撮影へ・この予約を引き直す・緊急の患者で撮る |
| 撮影のボタン | 撮影・撮影して送る・送る |
| PACS のボタン | C-ECHO・再送・失敗をすべて再送 |
| 状態 | 待ち・送信中・送れた・失敗・確認待ち・確認済・確認の失敗・確認の時間切れ |
| C-ECHO の結果 | つながった（○ ms）・つながらない（理由） |
| 止める知らせ | この予約は別の装置の予定です／予約は MR、テンプレートは CT です／「髙」は ISO 2022 IR 87 で表せません（Patient's Name の漢字） |
| 0 件 | 予約はありません。条件を広げるか、緊急の患者で撮ってください |

- **相手から来る値（ワークリストの値・相手の Status の文など）は、
  画面に出すとき必ずエスケープする**（Jinja2 の自動エスケープを切らない。
  `|safe`・`Markup` を相手から来る値に使わない。HTMX の部分の応答も同じ）。
  制御文字・双方向の制御文字は 11.7 と同じく見える形にする

### 10.9 待ち受けと認証

**既定は手元（`127.0.0.1`）だけで待ち受け、認証は付けない。** 例外は
1つ：手元の外（`0.0.0.0` など）で待ち受けるときは、簡単な認証を
必須にする。

- 手元の外で待ち受ける設定で、パスワードの設定が無ければ起動しない
  （エラーで止まり、理由を出す）
- 認証は HTTP Basic（利用者 1 人）。パスワードは環境変数
  `DTG_WEB_PASSWORD_FILE` が指すファイルから読む。既定値を置かない。
  設定ファイルに平文で書かせない
- 書き込みの要求（POST）は、`Origin` の見出し（無ければ `Referer`）の
  住所とポートが、要求の `Host` と同じときだけ受ける（他のサイトからの
  要求を断る。どちらも無い要求も断る）。あわせて、起動のたびに作る
  token（CSRF の token）を頁に埋め、POST の見出し `X-CSRF-Token` か
  フォームの欄 `csrf_token` で返させ、合わなければ断る（403）
- 手元（`127.0.0.1`・`::1`・`localhost`）で待ち受けるときは、`Host` の
  見出しが手元の名前のときだけ受ける（DNS rebinding で、他のサイトの
  頁から手元の画面を読ませないため）
- 利用者の名前は `dtg` に決める。パスワードのファイルは起動のときに
  1回読み、前後の空白と改行を除く。ファイルが無い・読めない・空なら
  起動しない。`DTG_WEB_PASSWORD_FILE` があれば、手元で待ち受けるときも
  認証を付ける
- 応答には `Content-Security-Policy`（自分の住所の物だけを読む。
  インラインのスクリプトを使わない）・`X-Content-Type-Options: nosniff`・
  `Referrer-Policy: same-origin`・`X-Frame-Options: DENY` を付ける
- HTTPS は持たない。網に出すときは前段の逆プロキシで TLS を付ける
  ことを README に書く
- 試験の道具なので、利用者の管理・二要素・監査の記録は持たない
  （tsunagi-dicom の 3.6 とは目的が違う）

---

## 11. CLI

`spec/04_cli.md` の形に合わせ、`python -m app.cli` のサブコマンドとして
足す。依頼の `dicom-gen` の名前は、いまの CLI の入口
（`python -m app.cli`）に合わせて使わない。

どのサブコマンドも次を持つ。

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--config PATH` | 設定のファイル（`modality:` の節を読む） | `config/app_config.yaml` |
| `-v, --verbose` | 詳しいログ（pynetdicom のログも DEBUG にする） | false |
| `--log-file PATH` | ログのファイル | `logs/dicom_generator.log` |

### 11.1 サブコマンド

| コマンド | 説明 | Phase |
|---------|------|-------|
| `echo` | 送り先・ワークリストの相手に C-ECHO | 3a |
| `worklist query` | ワークリストを引いて一覧を出す | 3a |
| `worklist show <鍵>` | 最後に引いた予約の1件の値を出す | 3a |
| `exam` | 予約（または緊急の患者）で撮る | 3a |
| `send` | 出力のフォルダの画像を送る | 3a |
| `queue list` | 待ち行列と履歴を出す | 3a |
| `queue retry` | 失敗を再送する | 3a |
| `commit` | 送った検査の保管の確認を求める | 3c |

### 11.2 echo

```bash
python -m app.cli echo --to PACS_TEST
python -m app.cli echo --worklist
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--to NAME` | 設定の送り先の名前 | 既定の送り先 |
| `--worklist` | ワークリストの相手に送る | false |

### 11.3 worklist query

```bash
python -m app.cli worklist query
python -m app.cli worklist query --date 20261018 --modality CT --json
python -m app.cli worklist query --patient-id P000001
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--date DATE` | `today`・`YYYYMMDD`・`YYYYMMDD-YYYYMMDD` | today |
| `--modality M` | モダリティ。`any` で条件にしない | 設定のテンプレートのモダリティ |
| `--station-aet AET` | 予定の AE タイトル。`any` で条件にしない | 自分の AE タイトル |
| `--patient-id ID` | 患者 ID | なし |
| `--patient-name PN` | 氏名（末尾の `*` を足す） | なし |
| `--accession ACC` | 受付番号 | なし |
| `--json` | JSON で出す（試験から使う） | false |

出力例（通常）：

```text
[INFO] Worklist: RIS_TEST  SpecificCharacterSet: ISO_IR 192
KEY         TIME   PATIENT_ID  ACCESSION  MODALITY  DESCRIPTION
3f9a1c0b2e  09:00  P000001     A0001      CT        胸部 CT
[INFO] 1 item(s). Saved to state/worklist_last.json
```

### 11.4 exam

```bash
# 予約で撮る（最後に引いた結果から）
python -m app.cli exam --from-worklist 3f9a1c0b2e -s 2 -i 1,20

# 予約を引き直してから撮って送る
python -m app.cli exam --from-worklist 3f9a1c0b2e --refresh \
  -m ct_generic -s 1 -i 20 --send

# 緊急の患者（予約なし）
python -m app.cli exam --emergency --patient-id E0001 \
  --patient-name "KINKYU^TARO=緊急^太郎" --birth-date 19800101 \
  --sex M -s 1 -i 10
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--from-worklist KEY` | 予約の鍵 | — |
| `--refresh` | 撮る前にその予約を引き直す | false |
| `--emergency` | 予約なし。`--patient-*` が必須 | false |
| `-m, --modality NAME` | テンプレート | 設定の既定 |
| `--profile NAME` | 装置のプロファイル（spec/13。Phase 3b の PR で足した。画面の「装置」と同じ） | 設定の既定（`default_profile`） |
| `--hospital NAME` | 病院テンプレート | 設定の既定 |
| `-s, --series N` | シリーズ数 | 1 |
| `-i, --images LIST` | 各シリーズの枚数 | 1 |
| `--pixel-mode MODE` | ピクセル | 設定の既定 |
| `--abnormal-level L` | 異常のデータ | none |
| `--charset C` | `auto`・`utf8`・`jis`・`jis_kana` | 設定の既定 |
| `-o, --output DIR` | 出力のフォルダ | 設定の既定 |
| `--send` | 作った後に既定の送り先へ送る | false |
| `--to NAME` | `--send` の送り先 | 既定の送り先 |
| `--study-description TEXT` | 検査の記述（`--emergency` のときだけ） | 空 |
| `--patient-id`・`--patient-name` | 緊急の患者の ID・氏名（PN。`--emergency` のとき必須） | — |
| `--birth-date`・`--sex` | 緊急の患者の生年月日（YYYYMMDD）・性別（M/F/O）。省くと空 | 空 |
| `--json` | 結果を JSON で出す | false |
| `--mpps` | MPPS を送る（Phase 3c。3a では作らない） | 設定 |

`--from-worklist` と `--emergency` はどちらか1つを必須にする。

- 出力は `<出力のフォルダ>/<受付番号か emergency>_<撮影の日時 YYYYMMDDHHMMSS>/`
  に書く（受付番号は 6.5 の決まりで名前に直す。同じ秒に同じ名前が
  あれば `_2`・`_3` を足す）。同じ予約で2回撮ると、別のフォルダに同じ
  Study の新しいシリーズができる
- `-i` の数は `-s` と同じ数にする（`quick` と同じ）
- 撮影の画面の「止める・確かめる」は、CLI では次のとおりにする
  - テンプレートと予約のモダリティが違う・値が長さの制約を超える・
    表せない字・読めない値：止める（終了コード 4）
  - 予約の予定の AE タイトルが自分と違う・Study Instance UID を作った・
    生年月日や性別が空：知らせ（`[NOTICE]`。`--json` では `notices`）を
    出して撮る

### 11.5 send・queue

```bash
python -m app.cli send output/modality/A0001_20261018090000/ --to PACS_TEST
python -m app.cli queue list --status failed
python -m app.cli queue retry --all
python -m app.cli queue retry --job 3
python -m app.cli queue retry --stale
```

- `send FOLDER`：フォルダの `*.dcm` を待ち行列に1件（1つの検査）として
  入れ、すぐに送る。`--to` が無ければ既定の送り先
- `queue list`：`--status` は `pending`（待ち）・`sending`（送信中）・
  `sent`（送れた）・`failed`（失敗）。`--json` で JSON
- `queue list`：止まった送信中（8.2）の件には `[STALE]` を付ける。
  `--json` では `stale` が `true`
- `queue retry`：`--all`（失敗の全部）・`--job ID`・`--stale`（止まった
  送信中の全部。失敗に戻してから送る）のどれか1つを必須にする。
  失敗のファイルだけを送り直す

### 11.6 終了コード

既存（0・1・2・3・4）に **5（通信のエラー）を足す**（2026-10-18 に
承認者が決めた）。通信の失敗（Association を張れない・断られた・
相手が Failure を返した・時間切れ）は 5 にする。`spec/04_cli.md` と
`AI_DEVELOPMENT_RULES.md` 8 の表も同じにする。

| コード | 意味 | この章で起きる例 |
|-------|------|------------------|
| 0 | 成功 | — |
| 1 | 一般のエラー | 生成の失敗 |
| 2 | 設定のエラー | `modality:` の節の誤り（`ModalityConfigError`） |
| 3 | I/O のエラー | 出力のフォルダに書けない |
| 4 | バリデーションのエラー | 予約の値が写せない（`WorklistMappingError`）・表せない字 |
| 5 | 通信のエラー | `AssociationError`・`WorklistQueryError`・`StoreError` |

- 結果は標準出力、エラーは標準エラー（`AI_DEVELOPMENT_RULES.md` 8）
- `--json` のときは標準出力に JSON だけを出す

### 11.7 相手から来る値を端末に出すとき

**ワークリストの値（氏名・記述など、相手から来る値）は、端末に出す前に
制御文字を見える形に置き換える。** 例外は無い。ESC・CSI・OSC などを
そのまま出すと、端末の表示や題を書き換えられるため。

- 置き換える字：C0（U+0000〜U+001F）・DEL（U+007F）・C1（U+0080〜
  U+009F）・Unicode の双方向の制御（U+061C・U+200E・U+200F・U+202A〜
  U+202E・U+2066〜U+2069）・行と段落の区切り（U+2028・U+2029）
- 通常の出力：`\x1b`・`\u202e` のような見える形にする
  （`app/cli/terminal.py` の `sanitize_for_terminal`）。標準エラーの
  エラーの文も同じ
- `--json`：同じ字を JSON の `\uXXXX` に直す（`json_for_terminal`）。
  読み戻すと元の値に戻る（値そのものは変えない）
- ログに相手から来る値を出すときは `%r` で出す（制御文字が逃げる）。
  Patient ID も相手から来る値として扱う
- 端末（標準エラー）に出すログは、整えた後の文を行ごとに
  `sanitize_for_terminal` に通す（改行は残す。例外の Traceback も同じ）。
  ファイルのログはそのまま

---

## 12. 設定

`config/app_config.yaml` に `modality:` と `web:` の節を足す。節の名前と
既定のポート（保管の確認の待ち受け 11113・画面 8080）は 2026-10-18 に
承認者が決めた。

```yaml
modality:
  ae_title: "DTG_CT01"
  station_name: "DTG_CT01"
  listen:                       # 保管の確認の結果を受ける待ち受け
    bind_address: "127.0.0.1"
    port: 11113
  state_dir: "modality_state"   # 予約の最後の結果・待ち行列（sqlite3）
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
    use_mpps: false
  destinations:
    - name: "PACS_TEST"
      ae_title: "PACS_TEST"
      host: "127.0.0.1"
      port: 4242
      storage_commitment: false
      timeout_seconds: 30         # C-ECHO・C-STORE の時間切れ
  default_destination: "PACS_TEST"
  retry:
    max_attempts: 0             # 0 = 自動で再送しない
web:
  bind_address: "127.0.0.1"
  port: 8080
```

- 画面は `python -m app.web`（`--config PATH`。既定は
  `config/app_config.yaml`）で起動する。`web:` の節が無ければ上の既定を使う
- 手元の外で待ち受けるときの認証は 10.9（パスワードは設定のファイルに
  書かず、`DTG_WEB_PASSWORD_FILE` が指すファイルから読む）

- 読み込みは `app/modality/config.py`（Pydantic）。Core からは読まない
- AE タイトルは 16 文字以内・空白だけを禁じる（PS3.5 の AE の VR）
- 例は手元の住所・例の名前だけにする。施設の名前・住所を書かない

---

## 13. ログ

`spec/09_logging.md` に従う。

- 通信の開始・終わり・相手の Status の値・件数を INFO で残す
- 患者の氏名・生年月日はログに出さない（`AI_DEVELOPMENT_RULES.md` 5）。
  出すのは予約の鍵・受付番号・SOP Instance UID まで
- pynetdicom のログは WARNING 以上だけを通す（既定）。`--verbose` で
  DEBUG にする

---

## 14. 試験

**実の PACS・RIS にはつながない。** 試験の中で pynetdicom の SCP を
手元（`127.0.0.1`・空いているポート）に立てて流す。

| 種類 | 置き場 | 中身 |
|------|--------|------|
| Core | `tests/core/test_worklist_mapping.py` | 6 章の表の行ごとに、予約あり・予約なしで写した値を確かめる（生年月日・性別が空の予約、Patient's Size を m のまま写す、予約なしで Request Attributes Sequence・Referenced Study Sequence が無いことを含む）。外の資源を使わない |
| 文字コード | `tests/core/test_worklist_charset.py` | 4つの選択それぞれで、漢字・かな・半角カナの氏名を書き出して読み戻す。表せない字で止まること |
| Modality | `tests/modality/test_worklist_scu.py` | 手元の MWL の SCP（試験の fixture）に C-FIND。条件の組、Pending の打ち切り、時間切れ、文字コードの読み取り |
| Modality | `tests/modality/test_store_scu.py` | 手元の Storage の SCP に C-STORE・C-ECHO。成功・Warning・Failure・つながらない |
| Modality | `tests/modality/test_commitment_scu.py` | 手元の SCP が別の Association で N-EVENT-REPORT を返す形と、同じ Association で返す形（Phase 3c） |
| Modality | `tests/modality/test_mpps_scu.py` | N-CREATE・N-SET の値。相手が断る形（Phase 3c） |
| 統合 | `tests/integration/test_modality_flow.py` | MWL の SCP → `exam --from-worklist` → 既存の `app/scp`（Storage SCP）が受ける。受けた画像の値が予約と合うこと |
| CLI | `tests/cli/test_modality_commands.py` | 各サブコマンドの終了コード・`--json` の形 |
| Web | `tests/web/` | FastAPI の TestClient。頁が開く・HTMX の部分の応答・手元の外で待ち受けて認証が無ければ起動しないこと・`Origin` と CSRF の token の確かめ・相手から来る値（`<script>`・制御文字）がエスケープされること・手元の MWL と Storage の SCP を相手に画面から「引く→選ぶ→撮る→送る」の一巡り |

- MWL の SCP の fixture は、予約を YAML（合成の患者だけ）から作り、
  `EVT_C_FIND` の handler で返す。文字コードを変えた応答も作れる
- ポートは試験ごとに空いているものを取る（固定のポートを使わない）
- 見た目の値の試験：入力の CSS の `@theme` の値が「10.2」の表と
  同じことを確かめる

---

## 15. 段（Phase）と完了の線

| 段 | 中身 | 完了の線 |
|----|------|----------|
| **3a** | ワークリスト（C-FIND）・予約からの生成（6 章・7 章）・送信（C-STORE・C-ECHO・待ち行列）を CLI で。Core の写し方、Service の引数の追加、`app/modality/`、例外、設定 | 14 章の Core・文字コード・Modality（worklist・store）・統合・CLI の試験が通る。既存の試験がすべて通る。08・04・WORKFLOW の層の図を更新 |
| **3b** | ウェブの画面（10 章）：ワークリスト・撮影・PACS・設定、見た目の基準、待ち受けと認証 | Web の試験が通る。手元で起動し、手元の MWL の SCP と Storage の SCP を相手に「予約を引く→選ぶ→撮る→送る→確かめる」が画面で通る。CSS を作り直して差が無い |
| **3c** | 保管の確認（N-ACTION・N-EVENT-REPORT・待ち受け）、MPPS（N-CREATE・N-SET）、画面と CLI の `commit`・`--mpps` | Modality（commitment・mpps）の試験が通る。試験用の Orthanc で保管の確認が「確認済」になることを手で確かめ、手順を README に書く |

- 3a の前に、この仕様と ADR-0011 の承認を得る（2026-10-18 に得た）
- 各段は別の PR（1PR 1目的）。各段で `spec/` の関係する文書を先に直す

---

## 16. 既知の制約

### 16.1 Orthanc の Worklists のプラグインと文字コード（2026-10-18 の実測）

`orthancteam/orthanc` の Docker イメージ 26.9.1、Worklists の
プラグイン 0.9.2 で、REST でワークリストを作り、C-FIND MWL
（pynetdicom）で引いた結果。

| 作るときの SpecificCharacterSet | 作れたか | 保存された値 | C-FIND の応答 |
|----------------------------------|----------|--------------|---------------|
| 指定なし（プラグインが ISO_IR 192 にする） | 作れた | 漢字・かな・英字ともそのまま | ISO_IR 192 で返り、読み戻した字は合っていた（生のバイト列は確かめていない） |
| `ISO 2022 IR 87` | 作れた | **氏名の漢字・かなが消えた**（エラーにならない）。検査の記述も一部だけ残った | 消えたまま返る |
| `ISO 2022 IR 13\ISO 2022 IR 87` | **作れない**（400 `Unknown encoding while creating DICOM from JSON`） | — | — |

この道具への影響：

- Orthanc の Worklists を相手にするとき、予約は UTF-8 で作る。
  この道具は `auto` で UTF-8 の画像を作る。JIS の画像が要る試験では、
  撮影の画面か `--charset` で `jis`・`jis_kana` を選ぶ
- ワークリストの値が既に消えていても、この道具は気づけない（応答は
  正しい形で来る）。漢字・かなの成分が空の予約を引いたときは、
  一覧に「漢字・かなが空」の印を出す

### 16.2 Orthanc の文字コードのそのほかの点（公開の資料）

- Orthanc は C-FIND の応答（ワークリストを含む）の文字コードに
  `DefaultEncoding` の設定を使う（Orthanc の設定の見本
  `Configuration.json` の注）
- C-FIND の応答で SpecificCharacterSet の複数の値を扱えるように
  なったのは 1.12.2（Orthanc の `NEWS`）
- ISO_IR 13 のときの円記号（0x5C）と値の区切り `\` の扱いは 1.12.9 で
  直った（同じ `NEWS`）

### 16.3 この道具の制約

- MPPS は Orthanc を相手に使えない（4.2）
- ワークリストの SCP（RIS の役）は持たない。試験の中だけで立てる

---

## 17. テンプレートの名前の決まり

### 17.1 決まり

**テンプレートの名前は一般の名前にし、商用の製品の名前・会社の名前を
使わない**（2026-10-18 に承認者が採った）。形は
`<モダリティ>_<部位や用途>_<番号や特徴>`（小文字・`_` 区切り）。
例：`ct_generic`・`ct_chest_5mm`・`mr_head_generic`。

- 公開のテンプレートと、公開の例のプロファイル（`profiles/examples/`）の
  名前・`manufacturer`・`manufacturers_model_name`・`station_name` に
  商用の名前を書かない（`DTG Synthetic CT` のような架空の名前にする）
- **実在の装置に寄せたいときは、装置のプロファイルにする**
  （`spec/13_device_profiles.md`。2026-10-18 に承認者が案 A を選んだ）。
  コンフォーマンスステートメントを読んで写し、リポジトリの外の置き場に
  置く。外の置き場のプロファイルには、この決まりを当てない（実在の装置の
  名前と、写した文書の題・版・入手先を書いてよい）
- 理由：公開のリポジトリで、実在の製品の出力と誤解されないため。
  tsunagi-dicom の原則 6（商用の製品の名前を使わない）とそろえる

### 17.2 名前を変えた（2026-10-18）

この決まりを採った PR で、CT のテンプレートを `ct_generic`
（`templates/modality/ct_generic.yaml`）にした。

- 中身の `manufacturer`・`model_name`・`manufacturers_model_name`・
  `station_name`・`description`・コメントも架空の名前
  （`DTG Synthetic`・`DTG Synthetic CT`・`DTG_CT`）にした。撮影の値
  （`ct_image`・`spatial`・`window_presets`）は変えていない
- 名前が出ていた 19 のファイル（テンプレート・コード・試験・例・
  仕様・ADR・README・WORKFLOW）をすべて直した。仕様の出典の一覧
  （`spec/06_dicom_rules.md`）から、適合性宣言の行を消した
  （**誤り**。テンプレートの目的は装置の擬態だった。spec/13 の PR で
  擬態の行を戻し、仕組みを装置のプロファイルにした。ADR-0012）
- **古い名前を読みに来た Job YAML・CLI には、プロファイルの置き場へ
  案内するエラーを出す**（`TemplateNotFoundError`。案内を `hint` に
  入れる。別名で黙って読まない。spec/13 の 7.3）。古い名前は商用の名前を
  含むため、コードには名前そのものでなく SHA-256 の値で持つ
  （`app/services/template_loader.py`）

---

## 18. 決まったこと（2026-10-18 に承認者が決めた）

承認者は、この章の旧版（決めてほしいこと）の8つをすべて推奨のとおりに
決めた。本文の該当の所も、この決まりに合わせてある。

| # | 論点 | 決まったこと | 本文 |
|---|------|--------------|------|
| 1 | この仕様と ADR-0011 | 受け入れた（状態は承認済み。ADR-0011 は Accepted） | 冒頭・ADR-0011 |
| 2 | 画面の技術 | (a) FastAPI＋Jinja2＋HTMX＋Tailwind CSS（standalone の実行ファイル） | 10.1 |
| 3 | 足す包み | `fastapi`・`uvicorn`・`jinja2`・`python-multipart`・`httpx`（試験用）を足してよい。足すのは Phase 3b の PR | 10.1 |
| 4 | 既存の PySide6 の GUI | 案 B：ウェブの画面が生成の機能も持てたら、別の PR で外す。それまでは凍結 | ADR-0011・`spec/05_gui.md` |
| 5 | CLI の終了コード | 5（通信のエラー）を足す | 11.6・`spec/04_cli.md` |
| 6 | テンプレートの名前 | 一般の名前にする決まりを採る。名前を変える PR は、この決まりを写す PR と同じ | 17 |
| 7 | 設定の節の名前・既定のポート | `modality:`・`web:`。待ち受け 11113・画面 8080 | 12 |
| 8 | 明るい地の主の色 | `#0969da`（白の上で 5.19:1）。明るい地の控えめな地は `#f6f8fa` | 10.2 |
| 9 | 暗い地の主の色 | `#1f6feb`（ボタンの地で白い字 4.63:1。前の `#2f81f7` は 3.75:1 で届かなかった） | 10.2 |

同じ日に、承認者は画面の見た目の方向も決めた：**すっきりした画面**
（余白を取り、部品を少なく、一画面にやることを1つ）。この道具は
診療のためではなく、治験やシステムの試験のスタブとして使うので、
機能は少なくてよい（10 章の冒頭）。

### 18.1 まだ決まっていないこと

（明るい地の `--color-muted` は Phase 3b の PR で `#eff2f5` に決めた。10.2）

- 暗い地で、主の色を文字（リンクなど）に使うときの色。`#1f6feb` は暗い地の上で
  文字には使えない（10.2）。使うときに明るい色を別に決める

---

## 19. 出典

2026-10-18 に読んだもの。

- DICOM PS3.4 2026d K.6.1「Modality Worklist SOP Class」
  （Table K.6-1、K.6.1.3.1 SCU Conformance）
- DICOM PS3.4 2026d C.2.2.2（Specific Character Set の扱い）
- DICOM PS3.17 2026d DD.1「Examples For The Usage of The Modality
  Worklist」
- DICOM PS3.17 2026d Annex B（Modality Worklist と MPPS の流れの図）
- DICOM PS3.3 C.12.1.1.2（Specific Character Set）、10.6
  （Request Attributes Macro。実装の段で属性の一覧を確かめる）
- IHE Radiology TF-2 Rev. 23.0（2025-08-08）：4.5「Query Modality
  Worklist [RAD-5]」（Table 4.5-1・4.5-2・4.5-3、4.5.4.1.2.1 の
  Note）、4.8「Modality Images Stored [RAD-8]」（4.8.1、
  4.8.4.1.1.1、4.8.4.1.2）
- IHE Radiology TF-2x Rev. 23.0（2025-08-08）：Appendix A、
  Table A.1-1（Simple Case）・A.1-2（Unscheduled Case）、
  注 IHE-A.1.1〜A.1.5
- Orthanc：DICOM Conformance Summary
  （`OrthancServer/Resources/DicomConformance.txt`）、
  `OrthancFramework/Sources/DicomNetworking/Internals/CommandDispatcher.cpp`、
  `OrthancServer/Resources/Configuration.json`、`NEWS`
  （いずれも GitHub の OrthancMirror の 2026-10-09 の版）
- Orthanc Book：「DICOM storage commitment」「Worklists plugin」
  （新しいもの・古いもの）
- pynetdicom（GitHub の main。最新のリリース v3.0.4）：
  `sop_class.py`・`association.py`・`events.py`
- tsunagi-dicom（GitHub の main、2026-10-18）：`docs/spec.md`（1・2・
  3.1・7）、`src/app/globals.css`、`src/components/layout/site-header.tsx`、
  `src/components/ui/button.tsx`・`table.tsx`、`package.json`
- Tailwind CSS の GitHub releases（v4.3.3 の standalone の実行ファイル）、
  Lucide の LICENSE（ISC）
