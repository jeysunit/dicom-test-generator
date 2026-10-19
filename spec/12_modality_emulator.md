# 12. モダリティのダミー（Modality Emulator）仕様

この文書は、モダリティのダミーの**現在の仕様**（通信・予約の写し方・
文字コード・送信・層と配置・設定・ログ）を持つ。

| 文書 | 中身 |
|------|------|
| この文書（spec/12） | 1〜9 章、12・13 章 |
| [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) | 10 章（ウェブの画面）、11 章（CLI） |
| [12b_decisions_and_limits.md](12b_decisions_and_limits.md) | 14 章（試験）、15 章（段）、16 章（既知の制約・実測）、17 章（テンプレートの名前）、18 章（決まったこと）、19 章（出典） |

**章の番号は、コード・試験・設定のコメントからの参照を保つため、元の
spec/12 のままにしてある。** そのため、この文書の章は 1〜9 と 12・13 で、
10・11 と 14〜19 は上の文書にある。本文の「10.5」「14 章」のような参照は、
上の表の文書の章を指す。

## 要約

この道具は、本物のモダリティと同じ順で動く。ワークリストを取得し
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

**状態**: 実装済み（Phase 3a・3b・3c）。決まったことは 12b の「18. 決まった
こと」。試験用の Orthanc での保管の確認の手の確かめ（12b の 15 章）は
未了。

**目的の線**: この道具は診療のためではなく、治験やシステムの試験の
スタブ（モダリティの役の代わり）に使う。機能は少なくてよい。

**Phase**: Phase 3a・3b・3c（12b の「15. 段」。状態は WORKFLOW.md）

**依存**: Phase 0（Core Engine）、Phase 1（Service Layer・CLI）

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
  ワークリストを取得 → 予約を選ぶ → 撮る（合成の画像）→ 送る → 確かめる
```

### 範囲に入れるもの

- C-FIND（Modality Worklist）の SCU
- C-STORE の SCU、C-ECHO の SCU
- Storage Commitment Push Model の SCU（選べる）
- MPPS（Modality Performed Procedure Step）の SCU（選べる）
- ウェブの画面（ワークリスト・撮影・PACS・設定）
- CLI（`worklist`・`exam`・`send`・`echo`・`queue`・`commit`・`mpps`）

### 範囲に入れないもの

- ワークリストの SCP（RIS の役）。試験の中だけで pynetdicom で立てる
- 画像を受け取って保存する Storage SCP（PACS の役）。受信は PACS の役目で、
  モダリティの擬態という目的の外にある（2026-10-20 に外した。
  [ADR-0013](../adr/0013-remove-storage-scp.md)）。試験の相手は、使う側が
  自分で用意する
- Query/Retrieve（C-MOVE・C-GET）の SCU
- HL7 の受信・送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査の記録など）
- 既存の PySide6 の GUI（`spec/05_gui.md`）の作り替え。
  扱いは ADR-0011 の案 B（ウェブの画面が生成の機能も持てたら外す。
  それまでは凍結）

### spec/05_gui.md との関係

- `spec/05_gui.md` は、生成の道具の PySide6 の画面（Phase 2a。凍結）の仕様。
  この文書の画面とは別のもの
- モダリティの画面はこの文書と 12a で決め、ウェブの画面にする
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
   └ 既定の条件（今日・自分の AE タイトル）でワークリストを取得する
2. 患者が来たら、一覧から予約を選ぶ
   └ 予約の値（氏名・ID・生年月日・受付番号など）を確かめる
   └ 必要なら「取得し直す」（その予約だけを最新にする。DD.1 の4つ目の例）
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
  （N-EVENT-REPORT と、相手からの疎通の確かめの C-ECHO だけを受ける）を
  持つ。待ち受けは保管の確認を有効にしたときだけ立てる（「8.3 保管の確認」・
  8.3.1）。画像を受け取る機能ではない

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

## 5. ワークリストの取得

### 5.1 取得の条件（Matching Keys）

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
- 取得の条件の組は、DICOM PS3.17 DD.1 の例（日付と AE タイトル、
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

- 取得の条件がすべて ASCII なら、問い合わせに Specific Character Set を
  入れない（既定の文字の集まり。PS3.4 C.2.2.2）
- 氏名などに ASCII でない字があれば、設定の
  `worklist.query_character_set`（既定 `ISO_IR 192`。`jis`・`jis_kana`
  の値も選べる）で書き、その値を問い合わせの Specific Character Set に
  入れる
- 相手がその文字コードを扱わないと、一致のしかたは相手次第になる
  （PS3.4 C.2.2.2）。0 件のときは画面に「日本語の条件は相手の文字コード
  の扱いに左右されます。患者 ID か受付番号でも取得してください」と出す
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
- 最後に取得した結果を状態の置き場（「12. 設定」の `state_dir`）に
  保存する。CLI はこれを読む
- 相手が Pending を返し続けて決めた時間（既定 30 秒）を過ぎたら
  C-CANCEL を送り、「途中まで」として受け取った分を出す
- `exam --refresh`（その予約だけを引き直す）のときは、時間の上限で
  途中までになったら撮らずに `WorklistQueryError`（終了コード 5）で止める。
  ほかの取得のしかたは途中までを返すまま

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
取得の条件に使い、予約の値が自分の AE タイトルと違えば、撮影の画面で
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
  ところは 03 に書いてある
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
- 画面の上の帯に、取得したワークリストの文字コードと、画像に使う文字
  コードを並べて出す（例：「ワークリスト：ISO_IR 192 → 画像：
  ISO 2022 IR 13\ISO 2022 IR 87」）

### 7.2 写せない字

- 選んだ文字コードで表せない字（例：UTF-8 の予約にある、JIS X 0208 に
  無い字）があれば、**黙って消さない**。撮影を止め、どの属性のどの字か
  を画面と CLI の標準エラーに出す
- 「表せない字を `?` に置き換えて撮る」は、異常のデータの一つとして
  明示して選んだときだけ行う。この選択は作っていない
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
  動きが違いうる。4つの選択それぞれの書き出しと読み戻しを試験で確かめる
  （12b の「14. 試験」）

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
- **送る前に、各ファイルを確かめる**（2026-10-19 に決めた）：symbolic link は
  断り、ファイルを `resolve()` して、送るフォルダの中の普通のファイルである
  ことを確かめる。外れたら1枚も送らない（`FileReadError`。最初の送信は
  待ち行列に入れる前に止め、再送はその件を失敗にして理由を残す）。最初の
  送信と再送の両方で確かめる（入れた後にファイルが替えられても送らない）
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

#### 8.3.1 結果を受ける道（2026-10-19 に決めた）

**結果は、どちらの道で来ても受ける。既定は「別の Association（待ち受け）」で
受け、N-ACTION の Association はすぐに離す。** 例外は1つ：送り先の設定
`commitment_wait_seconds` に秒を入れたときだけ、N-ACTION の後にその秒まで
同じ Association を開けたまま待ち、そこで来た N-EVENT-REPORT も受ける。

- 理由：主な試験の相手（Orthanc）は結果を別の Association で返す（4.2）。
  同じ Association で待つと、別の道で返す相手のときに毎回その秒だけ画面が
  止まる。同じ Association でしか返さない相手のときだけ秒を入れればよい
- どちらの道でも、受け取りの処理（下の 8.3.2）は同じ1つを通す
- 待ち受けは `modality.listen`（既定 `127.0.0.1:11113`）で立てる。受ける
  SOP Class は Storage Commitment Push Model と Verification（相手からの
  疎通の確かめ）だけ。呼ばれる AE タイトルが自分の AE タイトルと違う
  Association は断る。相手が SCP の役を求める役の交渉（SCP/SCU Role
  Selection）は受ける
- 別の道は、相手が Orthanc のときは `DicomModalities` にこの道具を登録して
  おく必要がある（4.2・12a の 10.7）

#### 8.3.2 受け取りの決まり（相手から来る値は信用しない）

- 結果の Transaction UID が、この道具が出して**まだ待っている**か時間切れに
  した要求の UID と合うときだけ受ける。合わない・UID の形でない・Event
  Information が無い・読めないときは何も書かずに Failure を返す
  （Event Type が 1・2 でなければ `0x0113`、ほかは `0x0110`）
- 別の道で来たときは、呼んできた AE タイトルがその要求の送り先の AE
  タイトルと同じときだけ受ける（違えば `0x0110`）
- **読む順と大きさの上限**（2026-10-19、Codex の指摘で足した）：Event
  Information の大きさが 1 MiB を超えれば、読まずに `0x0110` を返す。読むときは
  先に Event Type・Transaction UID と呼んできた AE だけを確かめ、合ったときだけ
  参照の並びを読む。参照の件数（Referenced SOP Sequence と Failed SOP
  Sequence の合計）が、その要求で問うた画像の数を超えれば、何も書かずに
  `0x0110` を返す。1 MiB は、1回の撮影の上限（2000 枚）の参照を十分に入れられる
  大きさ。つながりの層（pynetdicom）が組み立てる前の大きさは、この道具では
  抑えない（待ち受けは既定で手元だけ）
- 要求に入れた画像の組（SOP Class UID と SOP Instance UID）だけを見る。
  Referenced SOP Sequence にあれば「確認済」、Failed SOP Sequence にあれば
  「確認の失敗」（Failure Reason の数を残す）。要求に無い組は捨てる（件数の
  上限の内で）。要求した
  のに結果のどちらにも無い組は「確認の失敗」（理由「結果に無い」）にする
- Event Type が 1 でも、Failed SOP Sequence があればその画像は失敗にする
  （書いてある方を信じる）
- 時間切れにした後に結果が来たら、その結果で置き換える（相手の最後の答えの
  方が確か）。記録に「遅れて来た」と残す
- 相手から来た値は、記録に `%r` で出す。画面には件数と状態の言葉だけを出し、
  相手の文は出さない（Failure Reason は `0x0112` のような数だけ）
- 状態の確かめと書き込みは1つの取引で行い、待っている（か時間切れの）要求に
  だけ書く。同じ要求に2つの結果が来たら、先に書いた方を残し、後の方には
  `0x0110` を返す。N-ACTION の失敗も、待っている要求だけを「確認の失敗」に
  する（先に届いた結果を上書きしない。2026-10-19、独立レビューの指摘で足した）

#### 8.3.3 いつ求めるか・待ち行列の状態

- ウェブの画面では、保管の確認を使う送り先へ1件が「送れた」になったら、
  すぐに N-ACTION を送る（再送で送れたときも同じ）。画面のプロセスが
  待ち受けを立てて結果を受ける
- CLI では自動で求めない。`commit --job ID` で求め、待ち受けを立てて
  結果か時間切れまで待つ（12a の 11.8）。画面が同じ待ち受けのポートで動いて
  いれば、CLI は待ち受けを立てられないので、その旨を出して止まる
- 求めるのは状態が「送れた」の件だけ。送れた画像（Success・Warning）の
  組を、送ったときに残した SOP Class UID・SOP Instance UID から集める
  （ファイルは読み直さない）
- 待ち行列の各件に、最後の要求の状態を持たせる：「確認待ち・確認済・
  確認の失敗・確認の時間切れ」。保管の確認を使わない送り先の件は「—」
- N-ACTION を送れない（Association を張れない・相手が Failure を返した）
  ときは「確認の失敗」にし、理由を残す。自動では求め直さない
  （`commit --job ID` で求め直す。新しい Transaction UID を作る）
- 時間切れ（送り先の `commitment_timeout_seconds`、既定 600 秒）は、
  待ち行列を読むたびに確かめて「確認の時間切れ」にする
- 撮影に使った装置のプロファイルが `services.storage_commitment: false`
  なら、その撮影の件には求めない（spec/13 の 8）。撮影の出力のフォルダと
  プロファイルの名前の組を状態の置き場に残して見分ける

### 8.4 MPPS（Phase 3c）

- ワークリストの相手（または別の MPPS の相手）ごとに「MPPS を使う」を
  選ぶ。既定は使わない（「4.2」のとおり Orthanc は受けない）
- 撮影の開始で N-CREATE（IN PROGRESS）、作り終わりで N-SET
  （COMPLETED）。撮影を取り消したら N-SET（DISCONTINUED）
- MPPS が失敗しても撮影と送信は止めない。失敗は画面と記録に出す

#### 8.4.1 送り先・送るとき・再送（2026-10-19 に決めた）

**MPPS は、ワークリストの相手の `use_mpps: true` のときだけ送り、送り先は
`modality.mpps:` の相手（書いていなければワークリストの相手）にする。**
例外は2つ：CLI の `exam --mpps`・`--no-mpps` はその撮影だけ設定を
上書きする。装置のプロファイルが `services.mpps: false` なら、設定で選んで
いても送らない（spec/13 の 8）。

- 「撮影の開始」は、撮影の値を確かめ終わり、画像を作り始める直前
  （N-CREATE）。「作り終わり」は画像を書き終えた直後（N-SET COMPLETED）
- 「取り消し」は、N-CREATE を送った後に撮影が止まったとき（画像を作る途中の
  誤り・表せない字など）。N-SET（DISCONTINUED）を送る。画面と CLI には
  撮影を取り消す操作を持たない（Phase 3b で削った）
- 予約に Study Instance UID が無いときは、N-CREATE より前にこの道具が
  UID を作り、その UID で画像も作る（MPPS と画像の Study をそろえる）
- 送る値は 6.4 のとおり。Performed Series Sequence は作った画像の
  ヘッダーから組む（シリーズごとに Series Instance UID・Series
  Description・Protocol Name と、画像の Referenced SOP Class・Instance UID）
- 送れない（Association を張れない・相手が Failure を返した・時間切れ）
  ときは、その知らせを状態の置き場の MPPS の待ち行列に「失敗」で残す。
  相手の Warning は送れた扱いにする
- 再送は `retry.max_attempts`（送信と同じ）の回数だけすぐに試し、それでも
  だめなら残す。残った分は CLI の `mpps retry` で送り直す（12a の 11.9）。順は
  必ず N-CREATE が先で、N-CREATE が送れていない件の N-SET は送らずに待つ
- **送れたとみなすのは、相手が Success か Warning を返したときだけ。例外は
  2つで、どちらも「前に同じ知らせを送り、応答が来なかった」と記録から言える
  ときに限る**（2026-10-19、独立レビュー（Codex）の指摘で直した）：
  1. N-CREATE に `0x0111`（同じ SOP Instance が既にある）が返り、前の
     N-CREATE が「応答なし」で終わっていた
  2. 終わりの N-SET に `0x0110`（終わった MPPS は更新できない。PS3.4
     F.7.2.2）が返り、前の同じ N-SET が「応答なし」で終わっていた
  - 理由：`0x0110` は「処理の失敗」の一般の値でもある。前に相手が Failure を
    返していた・前に送っていない（N-CREATE を待って保留していた N-SET の
    初回）なら、届いていたとは言えないので失敗のまま残す
  - 「応答なし」は、Association を張って要求を送った後に、応答が来ないまま
    時間切れ・切断になったこと。Association を張れなかった・相手が Failure を
    返した・Presentation Context を断られたは「応答なし」に数えない
  - 待ち行列の行に、操作ごと（N-CREATE・N-SET）に「応答なしで終わった」印を
    残す（送り直しのすぐの2回目以降も、この印で決める）
- 送り直しは、設定の `use_mpps` が false でも、待ち行列に送れていない知らせが
  あれば行う（`exam --mpps` で作った分。同じ日に足した）
- **送り先は行に固定する**（同じ日、Codex の指摘で足した）：N-CREATE を作る
  ときの MPPS の相手の AE タイトル・住所・ポートを行に残し、送り直しも必ず
  その相手へ送る。設定を後で変えても、新しい相手には送らない（元の相手に
  IN PROGRESS が残る・別の相手に患者の値を送ることを避ける）。時間切れの秒は
  いまの設定の値を使う
- **同じ行を2つの手順が同時に送らない**（同じ日、Codex の指摘で足した）：
  送る前に、行の「送る権利の札」を条件つきの更新で取る（札が空か、札を取って
  から 10 分より長く経った行だけ）。取れた手順だけが送り、終わったら札を
  外す。取れなかった行は、その回は送らずに残す（`mpps retry` の結果では
  送れていない件に数える）。画面の撮影・複数の CLI の間で効く
- 画像を書けなかった（OSError）・作った画像のヘッダーを読めないときも、
  N-CREATE を送っていれば DISCONTINUED を残す（開いたままにしない）
- MPPS の SOP Instance UID はこの道具が作る（2.25 の UUID の形）

#### 8.4.2 手元で試す受け手（2026-10-19 に決めた）

**保管の確認の SCP と MPPS の SCP は、試験の中の偽の相手
（`tests/modality_peers.py`）だけで作る。この道具の機能として受け取る側を
持たない。** 例外は無い。

- 理由：ワークリストの SCP（RIS の役）を試験の中だけで立てるのと同じ
  決まりにそろえる（1 章の「範囲に入れないもの」）。受け取る側を持つと、
  受けた画像の台帳・結果を返す先の設定（相手の AE・住所・ポート）・
  MPPS の保存が要り、試験のスタブとしての機能が増える（12a の 10 章の冒頭の
  「機能を足すより削る」）。2026-10-20 には、画像を受け取って保存する
  Storage SCP も同じ理由で外した（ADR-0013）
- 手で試すとき：保管の確認は試験用の Orthanc を相手にする（12b の 15 章）。
  MPPS は受ける試験の相手（RIS など）が要る。Orthanc は受けない（4.2）

---

## 9. 層と配置

### 9.1 決まり

**モダリティの通信と手順は `app/modality/` に置き、Service Layer の
一部として扱う。** UI（`app/cli/`・`app/web/`）からだけ呼ばれ、
下の `app/services/` と `app/core/` を使う。例外は2つ。

1. 予約から生成の設定への写し方（6 章）は、通信の要らない Pure な
   処理なので `app/core/worklist_mapping.py` に置く
2. 保管の確認の待ち受け（N-EVENT-REPORT を受ける）は SCP の働きだが、
   SCU の手順の一部なので `app/modality/` に置く

### 9.2 依存の向き

```text
Web (app/web/) ─┐
CLI (app/cli/) ─┤→ Modality (app/modality/) → Service (app/services/)
                │                                   ↓
GUI (app/gui/) ─┴→ Service (app/services/) ──→ Core (app/core/)
```

- `app/modality/` が import する**このプロジェクトの中の**層は
  `app/services/`・`app/core/` だけ。`app/cli/`・`app/web/`・
  `app/gui/` を import しない。外の包み（pynetdicom・
  pydicom・Pydantic・PyYAML）と標準ライブラリ（`sqlite3` など）は
  使ってよい。通信と永続化を Core へ移さない（Core は Pure のまま）
- `WORKFLOW.md` の層の図にも同じ層（`app/modality/`・`app/web/`）がある

### 9.3 ファイルの配置

```text
app/
├── core/
│   ├── worklist_mapping.py   # 予約 → 生成の設定（Pure）
│   ├── worklist_charset.py   # 画像の文字コードの決め方・表せない字（Pure）
│   └── models.py             # WorklistItem・ScheduledContext を足す
├── modality/
│   ├── __init__.py
│   ├── config.py             # 自分の AE・相手・送り先（Pydantic）
│   ├── association.py        # Association を張る共通の部分
│   ├── worklist_scu.py       # C-FIND MWL
│   ├── store_scu.py          # C-STORE・C-ECHO
│   ├── commitment_scu.py     # Storage Commitment（N-ACTION・待ち受け・結果の読み取り）
│   ├── mpps_scu.py           # N-CREATE・N-SET（送る値の組み立てを含む）
│   ├── mpps_queue.py         # MPPS の知らせの待ち行列（sqlite3。Phase 3c）
│   ├── queue.py              # 待ち行列と履歴・保管の確認の要求（sqlite3）
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
    └── modality_commands.py  # worklist・exam・send・echo・queue・commit・mpps
```

この図は、モダリティのダミーが足したファイルだけを示す（`app/core/` の
ほかのモジュールは spec/02、`app/web/` の細部は 12a）。

### 9.4 Service Layer の変更（Phase 3a）

- `StudyGeneratorService.generate` に、外から Study Instance UID と
  予約の値（`ScheduledContext`）を渡せる引数を足した。渡さなければ
  いまと同じ動き（既存の試験を変えない）
- 既存の `GenerationConfig` の制約（Patient ID 16 文字・Accession
  Number 16 文字など）は予約の値にも当てる。予約の値が制約を超えたら
  撮影の画面で止め、どの値かを出す

### 9.5 例外

`spec/08_error_handling.md` の階層に、次を足した。

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
    use_mpps: false               # MPPS を送るか（Phase 3c。8.4.1）
  mpps: null                      # MPPS の送り先（Phase 3c）。null はワークリストの相手
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
      commitment_timeout_seconds: 600  # 保管の確認の結果を待つ秒（8.3）
      commitment_wait_seconds: 0  # 同じ Association で結果を待つ秒。0 は待たない（8.3.1）
      timeout_seconds: 30         # C-ECHO・C-STORE・N-ACTION の時間切れ
  default_destination: "PACS_TEST"
  retry:
    max_attempts: 0             # 0 = 自動で再送しない
  max_images_per_exam: 2000     # 1回の撮影の合計の枚数の上限（12a の 10.5）
web:
  bind_address: "127.0.0.1"
  port: 8080
```

- 画面は `python -m app.web`（`--config PATH`。既定は
  `config/app_config.yaml`）で起動する。`web:` の節が無ければ上の既定を使う
- 手元の外で待ち受けるときの認証は 12a の 10.9（パスワードは設定のファイルに
  書かず、`DTG_WEB_PASSWORD_FILE` が指すファイルから読む）

- 読み込みは `app/modality/config.py`（Pydantic）。Core からは読まない
- AE タイトルは 16 文字以内・空白だけを禁じる（PS3.5 の AE の VR）
- 例は手元の住所・例の名前だけにする。施設の名前・住所を書かない
- 設定・状態の置き場のファイル（`worklist_last.json` など）が検証で外れたとき、
  誤りの文は「項目の名前: 原因」だけにし、入っていた値を出さない（壊れた
  保存のデータに患者の氏名が入りうるため。画面・CLI・ログとも同じ。
  2026-10-19 に決めた）
- 3c の項目の範囲：`commitment_timeout_seconds` は 1〜86400、
  `commitment_wait_seconds` は 0〜60（同じ Association で長く待たせない）。
  `mpps:` の AE タイトル・ポートは送り先と同じ決まり
- 待ち受け（`listen.bind_address`）の既定は `127.0.0.1`。手元の外で受ける
  ときだけ設定で変える。待ち受けが起動しただけで外のどこからでも
  Association を受けないようにするため

---

## 13. ログ

`spec/09_logging.md` に従う。

- 通信の開始・終わり・相手の Status の値・件数を INFO で残す
- 患者の氏名・生年月日はログに出さない（`AI_DEVELOPMENT_RULES.md` 5）。
  出すのは予約の鍵・受付番号・SOP Instance UID まで
- pynetdicom のログは WARNING 以上だけを通す（既定）。`--verbose` で
  DEBUG にする
