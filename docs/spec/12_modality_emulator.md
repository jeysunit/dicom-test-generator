# 12. モダリティエミュレーター

この文書は、モダリティエミュレーターの通信・予約の値の転記・文字コード・送信・
モジュールと配置・設定・ログ・既知の制約を定める。Web 画面と CLI は
[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) にある。

| 文書 | 章 |
|------|----|
| この文書（spec/12） | 1〜9 章、12〜15 章 |
| [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) | 10 章（Web 画面）、11 章（CLI） |

章番号は、コード・テスト・設定のコメントが番号で参照しているため、2つの文書を
通して振っている。本文の「10.5」のような番号だけの参照は、上の表の文書の章を
指す。

## 要約

DTG は、本物のモダリティと同じ順序で動作する。ワークリストを取得し
（C-FIND MWL の SCU）、予約の値を転記した画像を作成し、PACS へ送信する
（C-STORE の SCU）。例外は3つある。

1. 予約の無い「緊急の患者」は、値を手入力し、IHE の予約なしの形式に従う
2. 保管確認（Storage Commitment）の SCU は選択できる形にする
3. MPPS（N-CREATE・N-SET の SCU）は、相手が受け付けるときだけ使う

画面は Web 画面（サーバー側で描画する。FastAPI・Jinja2・HTMX・Tailwind CSS）で
作成する。同じ操作を CLI でも行え、自動テストから使える。

DTG は診療のためではなく、システムのテストでモダリティの代わりに使う。機能は
少なくてよい。

設計の判断：[ADR-0011](../decisions/0011-modality-emulator.md)・
[ADR-0017](../decisions/0017-copy-study-instance-uid-from-worklist.md)・
[ADR-0018](../decisions/0018-stop-on-unrepresentable-characters.md)・
[ADR-0019](../decisions/0019-storage-commitment-result-path.md)・
[ADR-0020](../decisions/0020-mpps-optional-with-retry-queue.md)・
[ADR-0021](../decisions/0021-test-only-commitment-and-mpps-peers.md)

> **Not for Diagnostic Use / 非医療機器。** 作成する画素は合成したもので、臨床に
> 使えない。本番の PACS への接続は範囲外。テスト用の PACS・RIS にだけ接続する。

---

## 1. 目的と範囲

### 目的

PACS・RIS・ビューアのテストで、モダリティの役を DTG に任せる。本物の装置を
使わずに、次の流れを繰り返し実行できるようにする。

```text
RIS（ワークリスト）→ モダリティ → PACS
  ワークリストを取得 → 予約を選択 → 撮影（合成の画像）→ 送信 → 確認
```

### 範囲に入れるもの

- C-FIND（Modality Worklist）の SCU
- C-STORE の SCU、C-ECHO の SCU
- Storage Commitment Push Model の SCU（選択できる）
- MPPS（Modality Performed Procedure Step）の SCU（選択できる）
- Web 画面（ワークリスト・撮影・PACS・設定）
- CLI（`worklist`・`exam`・`send`・`echo`・`queue`・`commit`・`mpps`）

### 範囲に入れないもの

- ワークリストの SCP（RIS の役）。テストの中だけで pynetdicom で起動する
- 画像を受信して保存する Storage SCP（PACS の役）。受信は PACS の役目で、
  テストの相手は利用者が用意する（[ADR-0013](../decisions/0013-remove-storage-scp.md)）
- Query/Retrieve（C-MOVE・C-GET）の SCU
- HL7 の受信・送信
- 本番の PACS への接続を前提にした機能（認証の強化・監査ログなど）
- Web 画面でのファイルの作成（Job YAML や `quick` に相当する画面）。ファイルの
  作成は CLI で行う（[ADR-0022](../decisions/0022-remove-desktop-gui.md)）

---

## 2. 用語

| 用語 | 意味 |
|------|------|
| 予約 | ワークリストの1件（Scheduled Procedure Step） |
| ワークリストの取得先 | MWL の SCP（RIS・Orthanc の Worklists など） |
| 送信先 | Storage の SCP（PACS） |
| 撮影 | 予約の値で合成の画像を作成すること |
| 緊急の患者 | 予約なしで撮影する患者（IHE の Unscheduled Case） |
| 保管確認 | Storage Commitment。送信した画像を相手が保管したかを問い合わせる |
| MPPS | 撮影の開始と終了を相手に通知する（N-CREATE・N-SET） |
| 送信キュー | 送信する画像の列。状態は 8.2 |
| 状態の保存先 | 最後に取得したワークリスト、送信キュー、MPPS のキューを置くフォルダ（設定の `state_dir`） |
| 予約のキー | DTG の中だけで使う予約の識別子（5.4） |

画面の言葉は、医療の現場の言葉を言い換えない。例：受付番号（Accession
Number）、検査、シリーズ、緊急、送信完了。

---

## 3. 操作の流れ

診療放射線技師の1日の操作に沿って書く。

```text
1. 朝、ワークリストの画面を開く
   └ 既定の条件（今日・自分の AE タイトル）でワークリストを取得する
2. 患者が来たら、一覧から予約を選択する
   └ 予約の値（氏名・ID・生年月日・受付番号など）を確認する
   └ 必要なら「取得し直す」（その予約だけを最新にする。DD.1 の4つ目の例）
3. 撮影の画面で、テンプレート・シリーズ数・画像数・異常のデータを選択する
   └ 予約の値は読み取り専用（書き換えない）
   └ MPPS を使うなら、撮影の開始で N-CREATE（IN PROGRESS）
4. 「撮影」で画像を作成し、送信キューに入れる
   └ MPPS を使うなら、作成の終了で N-SET（COMPLETED）
5. PACS へ送信する（撮影の画面の「撮影して送信」なら続けて送信する）
   └ 送信完了・送信失敗を確認する。失敗は再送
6. 保管確認を使うなら、結果（確認済・確認の失敗）を確認する
7. 予約の無い患者が来たら「緊急の患者」で撮影する
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
  `send_n_set` を使う（pynetdicom の公開 API。バージョンは requirements.txt の範囲）
- 保管確認の結果（N-EVENT-REPORT）は、相手が**別の Association で**送信してくる
  ことが多い。受け取るために、DTG は小さな待ち受け（N-EVENT-REPORT と、相手からの
  疎通確認の C-ECHO だけを受け付ける）を持つ。待ち受けは保管確認を有効にした
  ときだけ起動する（8.3.1）。画像を受信する機能ではない
- **どの Association でも、選んだ装置（12 章）の AE タイトルを Calling AE Title に
  する**（ADR-0023）。C-FIND・C-STORE・C-ECHO・MPPS・保管確認の N-ACTION のすべて。
  例外は3つ：画像の送信は画像を作った装置の AE タイトルで名乗る（8.2）。送信の件・
  MPPS の行の再送は、作ったときの AE タイトルで名乗る（8.2・8.4.1）。保管確認の要求は、
  件を作った装置の AE タイトルで送る（8.3.1）
- 相手が A-ASSOCIATE-RJ の理由 3「calling-AE-title-not-recognized」（PS3.8 9.3.4）で
  拒否したら、「相手が AE タイトル DTG_MR01 を受け付けませんでした。相手の側に、
  この装置の AE タイトルを登録してください」と知らせる（送信なら送信失敗の理由に
  なる）。PACS・RIS には、使う装置の AE タイトルをすべて登録しておく

### 4.2 Orthanc の対応

公開の資料とソースで確認した（出典は 15 章）。

| 機能 | Orthanc | 根拠 |
|------|---------|------|
| C-ECHO・C-STORE・C-FIND（MWL）の SCP | 受け付ける | DICOM Conformance Summary（ソースの `DicomConformance.txt`） |
| Storage Commitment の SCP | 受け付ける（1.6.0 から。Push Model だけ。結果は非同期で、別の Association で返す） | Orthanc Book「DICOM storage commitment」 |
| MPPS（N-CREATE・N-SET）の SCP | **受け付けない** | Conformance Summary に記載が無い。`CommandDispatcher.cpp` が扱う DIMSE は C-ECHO・C-STORE・C-FIND・C-MOVE・C-GET・N-ACTION・N-EVENT-REPORT だけで、ほかは `DIMSE_BADCOMMANDTYPE` |

したがって、**MPPS は相手が受け付けるときだけ使う**。既定は無効。Orthanc を相手に
するときは無効のままにする。有効にして相手が拒否したら、撮影は止めず、MPPS の
失敗として画面とログに出す。

Orthanc の保管確認では、要求元のモダリティを `DicomModalities` に登録しておく
必要がある（結果の返送先の AE タイトル・ホスト・ポートを Orthanc が知るため。
Orthanc Book）。設定の画面に、その旨と DTG の待ち受けの AE タイトル・ポートを
表示する。

---

## 5. ワークリストの取得

### 5.1 検索条件（Matching Keys）

| 条件 | Tag | 既定 | 画面 | 出典 |
|------|-----|------|------|------|
| 予定日（Scheduled Procedure Step Start Date） | (0040,0002) | 今日（範囲 `今日-今日` で送信する） | 今日・明日・日付の指定・絞らない | RAD TF-2 Table 4.5-2 |
| モダリティ | (0008,0060) | テンプレートのモダリティ | 選択・空 | 同上 |
| 予定の装置の AE タイトル（Scheduled Station AE Title） | (0040,0001) | 自分の AE タイトル | 「装置の AE タイトル」の欄：この装置で絞る・絞らない | 同上 |
| 患者 ID | (0010,0020) | 空 | 入力 | RAD TF-2 Table 4.5-1 |
| 患者の氏名 | (0010,0010) | 空 | 入力（各成分の末尾に `*` を追加する） | 同上 |
| 受付番号 | (0008,0050) | 空 | 入力 | 同上 |
| Requested Procedure ID | (0040,1001) | 空 | CLI だけ | 同上 |

- 予定日・モダリティ・AE タイトルは Scheduled Procedure Step
  Sequence (0040,0100) の中に入れる（PS3.4 K.6.1.2.2）
- 日付は範囲で送信する。単一の値の日付の照合方法が相手によって異なりうるため、
  IHE は範囲（`<今日>-<今日>`）を推奨している（RAD TF-2 4.5.4.1.2.1 の Note）
- 氏名の各成分の末尾に `*` を追加する（同じ Note の推奨）。利用者が `*` を入力
  したときは追加しない
- 検索条件の組み合わせは、DICOM PS3.17 DD.1 の例（日付と AE タイトル、日付と
  モダリティ、患者ごと）に合わせる

### 5.2 返却を求める値（Return Keys）

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
- Body Part Examined (0018,0015)（返ってくれば）。MWL の標準の返却の値ではないので、
  返さない RIS が多い。最上位か Scheduled Procedure Step Sequence の中のどちらかを
  読み、撮影のルーチンを当てるのに使う（[ADR-0025](../decisions/0025-exam-routines.md)）

Requesting Physician (0032,1032) は予約の詳細に「依頼医」として出すだけで、画像には
転記しない（6.2 の表に無い。IHE RAD TF-2x Table A.1-1 の転記の対象でもない）。
Referring Physician's Name (0008,0090) は「紹介医」として出し、画像に転記する。
(0032,1032) は Imaging Service Request を依頼した医師（PS3.3 C.4.12）、(0008,0090) は
患者の紹介医（PS3.3 C.7.2.1）で、別の属性である。

### 5.3 問い合わせの文字コード

- 検索条件がすべて ASCII なら、問い合わせに Specific Character Set を入れない
  （デフォルトの文字セット。PS3.4 C.2.2.2）
- 氏名などに ASCII 以外の文字があれば、設定の `worklist.query_character_set`
  （既定 `ISO_IR 192`。`jis`・`jis_kana` の値も選択できる）でエンコードし、その値を
  問い合わせの Specific Character Set に入れる
- 相手がその文字コードを扱えないと、照合の結果は相手次第になる
  （PS3.4 C.2.2.2）。0 件のときは画面に「日本語の条件は相手の文字コードの扱いに
  左右されます。患者 ID か受付番号でも取得してください」と表示する
- 画像の文字コードの `auto`（7 章）は、問い合わせには使わない

### 5.4 応答の扱い

- 応答の Specific Character Set を読み取り、値を Python の文字列にデコードする
  （pydicom）。デコードできない値は「読めない値」として画面に表示し、その予約は
  撮影に進めない。転記する Sequence の中の値（入れ子を含む）も検証し、
  `ReferencedStudySequence>ReferencedSOPClassUID` のように `Sequence>属性` の形で
  名前を残す。Sequence の中の UID（VR が UI）は、UID の形式（6.5）でなければ
  読めない値とする
- 一覧の1件ごとに、DTG の中だけで使うキー（予約のキー）を付ける。キーは
  `Study Instance UID`・`Requested Procedure ID`・
  `Scheduled Procedure Step ID`・`Accession Number` をこの順に `|` で連結した
  文字列（UTF-8）の SHA-1 の16進数の先頭 10 桁。CLI の `--from-worklist <キー>` で
  使う
- 最後に取得した結果を状態の保存先に保存する。CLI はこれを読み込む
- 相手が Pending を返し続けて設定した時間（既定 30 秒）を過ぎたら C-CANCEL を
  送信し、受け取った分を「途中まで」として出力する
- `exam --refresh`（その予約だけを再取得する）のときは、時間の上限で途中までに
  なったら撮影せずに `WorklistQueryError`（終了コード 5）で停止する。ほかの
  取得方法では途中までの結果を返す

### 5.5 応答の上限

**相手が返す応答は、受け取りながら数え、上限を超えたら C-CANCEL を送信して
Association を切断し、`WorklistQueryError`（終了コード 5）で停止する。** 途中まで
受け取った分は出力しない。例外は1つ：時間の上限（`timeout_seconds`）は 5.4 の
とおり C-CANCEL して「途中まで」を出力する。

| 上限 | 設定（`modality.worklist`） | 既定 |
|------|------------------------------|------|
| 件数 | `max_results` | 1000 |
| 1件のサイズ（Implicit VR で書き出したときのバイト数） | `max_item_bytes` | 256 KiB |
| 合計のサイズ | `max_total_bytes` | 16 MiB |
| C-CANCEL の後に返し続ける時間 | `timeout_seconds` と同じ長さ | 30 秒 |

- 上限は、その件を一覧に追加する前に確認する。1件のサイズは、pynetdicom が1件を
  受け取った後でしか測れない（受け取りの途中で止める手段が無い）。1件をメモリに
  載せられるかは pynetdicom の受け取りに任せる
- C-CANCEL の後も相手が返し続けたら、待つのは `timeout_seconds` の分だけにし、
  Association を切断して `WorklistQueryError` にする

---

## 6. 予約から画像への値の転記

### 6.1 規則

**予約にある値は、そのまま転記する。** 予約に無い値は、DTG が作成するか空にする。
出典は IHE RAD TF-2x Appendix A の Table A.1-1（予約どおりの形式）と Table A.1-2
（予約なしの形式）。IHE は、モダリティが予約の値を画像のヘッダーに入れることを
求める（RAD TF-2 4.8.1・4.8.4.1.2）。

### 6.2 表

「転記」は予約の値をそのまま使う。「作成」は DTG が作成する。

| 画像の属性 | Tag | 予約あり | 予約なし（緊急） | 出典 |
|------------|-----|----------|------------------|------|
| Specific Character Set | (0008,0005) | 「7. 文字コード」で決める | 設定の文字コード | PS3.4 K.6.1.3.1、PS3.3 C.12.1.1.2 |
| Patient's Name | (0010,0010) | 転記 | 手入力 | RAD TF-2 Table 4.5-3 |
| Patient ID | (0010,0020) | 転記 | 手入力（仮の ID の案を表示する） | 同上 |
| Issuer of Patient ID | (0010,0021) | 転記（あれば） | 空 | 同上 |
| Patient's Birth Date | (0010,0030) | 転記。**空なら空で転記する**（6.3） | 手入力 | 同上、PS3.4 Table K.6-1（Type 2） |
| Patient's Sex | (0010,0040) | 転記。**空なら空で転記する**（6.3） | 手入力 | 同上 |
| Patient's Weight | (0010,1030) | 転記（あれば。kg） | 出力しない（CLI では入力しない） | 同上 |
| Patient's Size | (0010,1020) | 転記（あれば。DICOM の m の値をそのまま転記する。内部の `Patient.size`（cm）は経由しない） | 出力しない（CLI では入力しない） | 同上、ADR-0007 |
| Patient's Age | (0010,1010) | 生年月日と検査日から算出。生年月日が空なら出力しない | 同じ | ADR-0008 |
| Study Instance UID | (0020,000D) | **予約にあれば転記する。無ければ生成する**（2.25） | 作成 | RAD TF-2x Table A.1-1・A.1-2、RAD TF-2 4.8.4.1.1.1、ADR-0017 |
| Accession Number | (0008,0050) | 転記 | **空（長さ0）** | 同上（IHE-A.1.1） |
| Issuer of Accession Number Sequence | (0008,0051) | 転記（あれば） | 空 | Table A.1-1 |
| Referenced Study Sequence | (0008,1110) | 転記（あれば） | 出力しない | Table A.1-1 |
| Referring Physician's Name | (0008,0090) | 転記 | 空 | RAD TF-2 Table 4.5-3 |
| Study ID | (0020,0010) | Requested Procedure ID | 作成（連番。`E` と 6 桁。状態の保存先の SQLite で採番する） | Table A.1-1（IHE の推奨） |
| Study Description | (0008,1030) | Requested Procedure Description。追加撮影では最初の撮影の値 | 撮影の画面の入力 | この仕様の決定（慣習。IHE の表には無い）、追加撮影は IHE-A.3.3 |
| Study Date・Time | (0008,0020)・(0008,0030) | 撮影した日時。追加撮影（6.3）では、その予約の最初の撮影の値 | 同じ | この仕様の決定、追加撮影は RAD TF-2x の IHE-A.3.3 |
| Procedure Code Sequence | (0008,1032) | Requested Procedure Code Sequence を転記 | 入れない | Table A.1-1 |
| Request Attributes Sequence | (0040,0275) | 1 項目を作成し、下の値を転記 | **属性を出力しない**（空の Sequence も置かない。Table A.1-2 の `n.a.`） | Table A.1-1・A.1-2 |
| >Requested Procedure ID | (0040,1001) | 転記 | — | Table A.1-1 |
| >Requested Procedure Description | (0032,1060) | 転記 | — | 同上 |
| >Scheduled Procedure Step ID | (0040,0009) | 転記 | — | 同上 |
| >Scheduled Procedure Step Description | (0040,0007) | 転記 | — | 同上 |
| >Scheduled Protocol Code Sequence | (0040,0008) | 転記 | — | 同上 |
| >Reason for the Requested Procedure | (0040,1002) | 転記（あれば） | — | 同上 |
| Performed Procedure Step ID | (0040,0253) | 作成（連番。`PPS` と 6 桁） | 作成（同じ） | Table A.1-1（IHE-A.1.2） |
| Performed Procedure Step Start Date・Time | (0040,0244)・(0040,0245) | その撮影の日時（ふつうは Study Date・Time と同じ。追加撮影では Study の日時と別） | 同じ | Table A.1-1（IHE の推奨）・A.1-3 |
| Performed Procedure Step Description | (0040,0254) | Study Description と同じ | 同じ | 同上 |
| Referenced Performed Procedure Step Sequence | (0008,1111) | MPPS を使うときだけ、その SOP Instance UID | 同じ | Table A.1-1（IHE-A.1.3） |
| Modality | (0008,0060) | テンプレートの値。予約の値と異なれば撮影の画面で停止する | テンプレートの値 | この仕様の決定 |
| Institution Name | (0008,0080) | 転記（あれば）。無ければ病院テンプレート | 病院テンプレート | Table A.1-1（Enterprise Identity Option のとき） |
| Station Name | (0008,1010) | 選んだ装置の Station Name。空なら病院テンプレート → 装置プロファイル → テンプレートの値 | 同じ | PS3.3 C.7.5.1、ADR-0023 |
| Series Instance UID・Frame of Reference UID | (0020,000E)・(0020,0052) | Series Instance UID はシリーズごとに生成する。Frame of Reference UID は既存の作成のとおり検査ごとに1つ生成する | 同じ | RAD TF-2 4.8.4.1.1.1 |
| Source Application Entity Title（File Meta） | (0002,0016) | 選んだ装置の AE タイトル | 同じ | PS3.10 |

Scheduled Station AE Title (0040,0001) は画像に転記する属性ではない。検索条件に
使い、予約の値が選んだ装置の AE タイトルと異なれば、撮影の画面で「この予約は別の
装置の予定です」と表示して確認を求める。

### 6.3 規則の補足

- **Study Instance UID は予約から転記する**
  （[ADR-0017](../decisions/0017-copy-study-instance-uid-from-worklist.md)）。
  予約に無いときは UID を生成し、撮影の画面に「予約に Study Instance UID が無いため、
  このツールが作りました」と表示する
- **生年月日・性別が空の予約も撮影できる。** どちらもワークリストでは Type 2 で、
  空で返ることがある（PS3.4 Table K.6-1）。空なら画像にも空で転記し（Type 2）、
  Patient's Age は出力しない。撮影の画面に「生年月日が空です」と表示する。既存の
  `Patient` のモデル（[03_data_models.md](03_data_models.md)。生年月日 8 桁・
  性別 M/F/O が必須）は変えず、予約からの経路では空を許す別のモデル
  （`ScheduledPatient`）を使う。作成の設定へ渡す処理は 03 に書いてある
- 異常のデータ（`abnormal`）は、転記した値にも適用される。異常のレベルを上げると、
  転記した値が壊れることがある。画面の「異常のデータ」にその旨を表示する
- **予約での撮影は1回で撮影済みになる**（[ADR-0024](../decisions/0024-exam-once-and-retake.md)）。
  画像を書き出し終えたら、予約の鍵ごとに、最初の撮影の Study Instance UID・Study
  Date・Study Time・Study Description と、作ったシリーズの数を状態の保存先の SQLite
  に記録する。撮影が止まった（MPPS を使うときは DISCONTINUED を送った）予約は記録
  しない。撮影済みの予約での通常の撮影は断る（`ValidationError`。CLI は終了コード 4）。
  ワークリストの一覧（画面・CLI）では、撮影済みの予約に「撮影済み」の印を付ける
- **撮り直しの形は設定 `modality.retake_mode` で選ぶ**（既定 `append`）
  - `append`：撮影済みの予約で「追加撮影」（CLI は `exam --append`）を行う。IHE の
    Append Case（RAD TF-2 4.6.4.1.2.3.3、RAD TF-2x Table A.1-3）に従い、Study Instance
    UID・受付番号・Request Attributes Sequence は元の予約と同じにし、シリーズは新しい
    Series Instance UID で作る（RAD TF-2 4.8.4.1.1.1 の「完了した手順にシリーズを
    追加しない」）。Study Date・Time・Description は最初の撮影の画像の値にする（説明が
    空なら空のまま。IHE-A.3.3）。Content Date・Time（画像を作った日時。PS3.3 C.7.6.1）
    と PPS の開始は、その撮影の日時にする。
    Series Number は前に作ったシリーズの続きから振る（この仕様の決定）。MPPS を使う
    ときは新しい MPPS の SOP Instance を作り、終わった MPPS には N-SET を送らない
    （PS3.4 F.7.2.2.2）。予約に Study Instance UID が無いときは、最初の撮影で作った
    UID を使う
  - `new_order`：撮影済みの予約は撮り直さず、「撮り直しの予約が要ります（RIS で
    新しい予約を作ってください）」と知らせる。RIS が作った撮り直しの予約（別の受付
    番号・Study Instance UID）をワークリストで取得し直し、通常の撮影で撮る
  - どちらの形でも、DTG は予約に Study Instance UID がある予約で新しい Study
    Instance UID を作らず、予約と異なる受付番号も作らない（RAD TF-2 4.8.4.1.1.1。
    受付番号は RIS が発番する）
  - 予約の鍵は Study Instance UID・Requested Procedure ID・SPS ID・受付番号から作る
    ので、RIS が予約の値を変えると別の予約として扱う
  - 撮影の記録が無かった前の版で撮った予約（Study Instance UID だけの記録）も、
    撮影済みとして扱う。その記録の日時・説明は、移した後の最初の撮影の値で埋め、
    その後の追加撮影はその値にそろえる
  - 同じ予約を、別のプロセス（画面と CLI など）が同時に撮らない。撮影済みの判定から
    記録までを、状態の保存先の SQLite の予約ごとの札で守る（ほかが撮っていれば「この
    予約は、ほかで撮影しています。終わってから撮ってください」）。撮影の間は札の時刻を
    1 分ごとに進め、30 分より長く進まない札は、撮影の処理が落ちたとみなして取り直す。
    札は持ち主だけが戻す（取り直された札は消さない）

### 6.4 MPPS に転記する値

N-CREATE（状態 `IN PROGRESS`）で送信する主な値：Scheduled Step Attributes
Sequence（Study Instance UID・Referenced Study Sequence・Accession Number・
Requested Procedure ID・Requested Procedure Description・Scheduled Procedure
Step ID・Scheduled Procedure Step Description・Scheduled Protocol Code
Sequence）、患者の値、Performed Procedure Step ID・Start Date・Start Time・
Description、Modality、Performed Station AE Title・Performed Station Name（撮影
した装置の AE タイトルと Station Name）。

N-SET（状態 `COMPLETED`・`DISCONTINUED`）で Performed Series Sequence
（シリーズごとの Series Instance UID と、作成した画像の SOP Class・Instance UID）と
End Date・Time を送信する。Performed Series Sequence はこの時点で空にしない
（PS3.4 F.7.2 の表 F.7.2-1 の Note 2）。画像が 1 枚も無ければ、画像の無い
シリーズの項目を 1 つ入れる（Series Instance UID は新しく生成し、Protocol Name は
`DTG`）。予約なしの形式では Referenced Study Sequence を空にする
（RAD TF-2x Table A.1-2）。

**MPPS そのものの** SOP Class・Instance UID は DIMSE のコマンドのフィールド
（N-CREATE の Affected SOP Class・Instance UID、N-SET の Requested SOP Class・
Instance UID）で送信し、データセットの最上位に SOP Class UID (0008,0016)・
SOP Instance UID (0008,0018) を置かない（IHE-A.1.4・A.1.5）。画像を参照する
Referenced SOP Class UID (0008,1150)・Referenced SOP Instance UID (0008,1155)
（Performed Series Sequence の中）は入れる。

### 6.5 予約の値は信用しない

**ワークリストの応答の値（Patient ID・受付番号・UID・氏名など）は、相手の SCP が
自由に設定できる、信用できない値として扱う。** 画像の属性には転記するが、ファイル・
フォルダの名前にはそのまま使わない。

- 名前に使うときは `[A-Za-z0-9._-]` 以外の文字を `_` に置き換え、長さを 64 文字
  までにし、空・`.`・`..` などのドットだけの名前は決まった名前（例：`emergency`・
  `UNKNOWN`）にし、Windows の予約名（`CON`・`NUL`・`COM1` など）は先頭に `_` を
  追加する（`app/core/path_safety.py`）
- 組み立てたパスは `resolve()` して、出力のルートフォルダの中にあることを確認する。
  外なら書き出さずに停止する（`FileWriteError`。終了コード 3）
- Job YAML の Patient ID から作るファイル名（既存の作成）も同じ規則で作る
- 撮影の前に、転記する値の形式を検証する。外れたら撮影せずに
  `WorklistMappingError`（終了コード 4）で停止する
  - Patient ID は空でなく 16 文字まで（spec/03 の `Patient`・`ScheduledPatient`
    と同じ制約。LO の 64 文字ではない）
  - Patient's Weight・Patient's Size は空か DS（PS3.5 の Decimal String：
    16 文字まで、`+`・`-` の付いてよい10進数、指数表記も可）
  - Study Instance UID は空か UID の形式（`^[0-9]+(\.[0-9]+)*$`・64 文字まで・
    各成分は `0` か、`0` で始まらない数字の並び。PS3.5 9.1）

---

## 7. 文字コード

### 7.1 規則

**画像の文字コードは、既定ではワークリストの応答に合わせる（`auto`）。**
設定と撮影の画面で、次の4つから選択し直せる。

| 選択肢 | 画像の Specific Character Set | 用途 |
|--------|-------------------------------|------|
| `auto`（既定） | ワークリストの応答と同じ値。応答に無いとき・予約なしのときは `character_set_fallback`（既定 `utf8`） | 本物のモダリティの多くの動作 |
| `utf8` | `ISO_IR 192` | UTF-8 の PACS |
| `jis` | `\ISO 2022 IR 87`（値 1 は空＝ISO 2022 IR 6） | 漢字を JIS で |
| `jis_kana` | `ISO 2022 IR 13\ISO 2022 IR 87` | 半角カナ＋漢字（日本の装置に多い組み合わせ） |

- `character_set_fallback` には `auto` を選べない（`utf8`・`jis`・`jis_kana` の
  どれか）。これで `auto` の行き先が必ず1つに決まる
- 値 1 が空の複数値は、値 1 を ISO 2022 IR 6 とみなす（PS3.3 C.12.1.1.2）。
  既存の病院テンプレートの `ISO 2022 IR 6\ISO 2022 IR 87` も `jis` と同じ意味で
  受け付ける
- 画面の上部のバーに、取得したワークリストの文字コードと、画像に使う文字コードを
  並べて表示する（例：「ワークリスト：ISO_IR 192 → 画像：ISO 2022 IR 13\ISO 2022
  IR 87」）

### 7.2 転記できない文字

**選択した文字コードで表現できない文字があれば、黙って削除せずに撮影を停止する**
（[ADR-0018](../decisions/0018-stop-on-unrepresentable-characters.md)）。
どの属性のどの文字かを、画面と CLI の標準エラー出力に出す。例：UTF-8 の予約に
ある、JIS X 0208 に無い文字。

- 検証するのは画像のすべての文字列の属性（予約から転記した値とテンプレートの値）。
  停止するのは書き出す前で、ファイルは残さない。撮影のために作成した出力フォルダが
  空のまま残るなら、それも削除する
- ISO 2022 IR 13 で受け付ける文字（ASCII のほか）は半角カナ（JIS X 0201 の
  0xA1〜0xDF）だけにする。`¥`・`‾` は IR 13 では 0x5C・0x7E になり、デコードすると
  `\`（値の区切り）・`~` に変わるため、表現できない文字として停止する。検証は
  pydicom.charset でエンコードしてデコードし、元の文字に戻るかで行う
- PN の漢字・かなの成分は、`jis`・`jis_kana` では ISO 2022 IR 87 の
  エスケープシーケンスで書く。`jis_kana` の英字の成分の半角カナは IR 13 で書く
- pydicom のバージョンによって、ISO 2022 IR 13 と IR 87 の組み合わせの書き出しの
  動作が異なりうる。4つの選択肢それぞれのエンコードとデコードをテストで確認する
  （[development.md](../development.md) の 4 章）

---

## 8. 送信

### 8.1 送信先

- 送信先は設定で複数持つ（名前・AE タイトル・ホスト・ポート）
- 1つを既定の送信先にする。撮影の画面の「撮影して送信」は既定の送信先へ送信する
- C-ECHO で疎通を確認できる（PACS の画面のボタン、CLI の `echo`）

### 8.2 送信キュー

| 状態（画面の表示） | 意味 | 次の操作 |
|--------------------|------|----------|
| 待機中 | 作成したが、まだ送信していない | 送信 |
| 送信中 | Association を確立して送信している | — |
| 送信完了 | C-STORE の応答が Success（0x0000）か Warning（0xB000 など） | 保管確認を要求・再送（新しい件） |
| 送信失敗 | Association を確立できない、相手が Failure を返した、タイムアウト | 再送 |

- 1回の送信では、1つの検査の画像を1つの Association で送信する
- Presentation Context は SOP Class ごとに 1 つ提示し、Transfer Syntax は
  ファイルの形式と Implicit VR Little Endian を並べる（提示する Abstract Syntax
  ごとに Implicit VR Little Endian を含める。PS3.5 10.1）。相手が Implicit を
  選べば、pynetdicom が Explicit VR Little Endian のファイルを Implicit に変換して
  送信する
- 失敗の理由（相手の Status の値・pynetdicom の例外の型）を記録する
- 件の受付番号は、件を作るときにフォルダの最初の画像の Accession Number (0008,0050)
  を読んで記録する（画面からの送信と CLI の `send` の両方）。読めなければ空のまま
  送信する。受付番号を記録していない前の件は、表示のときに画像から読んで補う
- 件を作るときに名乗る AE タイトルは、画像を作った装置の AE タイトル（最初の画像の
  Source Application Entity Title が設定の装置のどれかならそれ。違えば選んだ装置）。
  撮った後に装置を切り替えても、画像・MPPS・送信の名乗りがそろう（ADR-0023）
- 件には、名乗った AE タイトルを記録する。再送（送信完了の件の再送でできる新しい件も）
  はその AE タイトルで名乗る。あとで装置を切り替えても変えない。AE タイトルの列が
  無い前の版の行は、既定の装置の AE タイトルで埋める
- 送信失敗の件の再送は、その件の送れていない画像だけを同じ件で送信する。自動の
  再送は既定でしない（設定 `retry.max_attempts` で回数を決めたときだけ）
- 送信完了の件も、回数の上限なしに再送できる。同じフォルダの画像をすべて、その件と
  同じ送信先へ、新しい件として送信する（元の件と、その保管確認の結果は変えない）。
  画像は作り直さないので、SOP Instance UID・Series Instance UID・Study Instance UID は
  最初の送信と同じ（PS3.5 9 の UID は1つの物を指す）。相手が同じ SOP Instance UID の
  2回目をどう扱うか（上書き・受け流し・Warning・Failure）は相手の実装による。DTG は
  応答の Status をそのまま記録する。送信中・待機中の件は再送しない
- 送信キューと送信の履歴は、状態の保存先の SQLite（標準ライブラリの `sqlite3`）に
  記録する。新しい外部パッケージは追加しない
- 画像のファイルは出力フォルダに残す（送信しても削除しない）。削除するのは利用者の
  操作だけ
- **送信する前に、各ファイルを検証する**：シンボリックリンクは拒否し、ファイルを
  `resolve()` して、送信するフォルダの中の通常のファイルであることを確認する。
  外れたら1枚も送信しない（`FileReadError`。最初の送信はキューに入れる前に停止し、
  再送はその件を失敗にして理由を記録する）。最初の送信と再送の両方で検証する
  （キューに入れた後にファイルが置き換えられても送信しない）
- 送信中にするのは、待機中・送信失敗の件だけ（条件付きの更新で、更新された行が
  無ければ停止する）。同じ件を2つの処理が同時に送信しない
- 送信中のまま 30 分より長く変化しない件は、送信の処理が途中で異常終了したと
  みなす（停止した送信中）。`queue list` に表示し、`queue retry --stale` で失敗に
  戻してから再送する
- 送信の間は、1ファイルを送信するたびにタイムスタンプを更新する（長い送信を停止と
  みなさない）。送信中にするたびに、送信のロックを表すトークンを発行し、タイムスタンプの
  更新と、結果・失敗の記録はトークンが一致するときだけにする。トークンが一致しない
  （停止とみなされて引き継がれた）処理は、残りを送信せずに停止する

### 8.3 保管確認

1. 送信完了の画像の SOP Class UID・SOP Instance UID の組を集め、
   N-ACTION（Action Type 1）で送信先に問い合わせる
2. 結果の N-EVENT-REPORT を、同じ Association か、DTG の待ち受け
   （別の Association）で受ける
3. Event Type 1（すべて成功）なら「確認済」、2（一部失敗）なら失敗した画像
   だけを「確認の失敗」にする
4. 設定した時間（既定 10 分）に結果が来なければ「確認の時間切れ」

- 送信先ごとに保管確認を使うかを選択する（既定は使わない）
- 待ち受けは、保管確認を使う送信先が1つでもあるときだけ起動する

#### 8.3.1 結果を受ける経路

**結果は、どちらの経路で来ても受ける。既定は別の Association（待ち受け）で
受け、N-ACTION の Association はすぐに解放する**
（[ADR-0019](../decisions/0019-storage-commitment-result-path.md)）。
例外は1つ：送信先の設定 `commitment_wait_seconds` に秒数を設定したときだけ、
N-ACTION の後にその秒数まで同じ Association を開いたまま待ち、そこで来た
N-EVENT-REPORT も受ける。

- どちらの経路でも、同じ受け取りの処理（8.3.2）を実行する
- 待ち受けは `modality.listen`（既定 `127.0.0.1:11113`）で起動する。受け付ける
  SOP Class は Storage Commitment Push Model と Verification（相手からの疎通確認）
  だけ。呼び出された AE タイトルが、設定の装置（12 章）のどの AE タイトルとも
  異なる Association は、理由 7「called-AE-title-not-recognized」で拒否する
  （PS3.8 9.3.4）。装置を切り替えた後も、前の装置あての結果を受けるため。相手が
  SCP の役を求める SCP/SCU Role Selection は受け付ける
- 要求には、要求を送った装置の AE タイトルを記録する。結果は、その AE タイトルあてに
  届いたものだけを、その要求の結果にする（ほかの装置あては `0x0110` を返す）。要求は
  件を作った装置の AE タイトルで送る（8.2）
- 別の経路で受けるときは、相手が Orthanc なら `DicomModalities` に DTG を登録して
  おく必要がある（4.2・10.7）

#### 8.3.2 受け取りの規則（相手から来る値は信用しない）

- 結果の Transaction UID が、DTG が発行して**まだ待っている**か時間切れにした要求の
  UID と一致するときだけ受け付ける。一致しない・UID の形式でない・Event
  Information が無い・読めないときは何も記録せずに Failure を返す（Event Type が
  1・2 でなければ `0x0113`、ほかは `0x0110`）
- 別の経路で来たときは、呼び出し元の AE タイトルがその要求の送信先の AE タイトルと
  同じときだけ受け付ける（異なれば `0x0110`）
- **読み取りの順序とサイズの上限**：Event Information のサイズが 1 MiB を超えれば、
  読まずに `0x0110` を返す。読むときは先に Event Type・Transaction UID と呼び出し元
  の AE だけを検証し、一致したときだけ参照の並びを読む。参照の件数（Referenced
  SOP Sequence と Failed SOP Sequence の合計）が、その要求で問い合わせた画像の数を
  超えれば、何も記録せずに `0x0110` を返す。1 MiB は、1回の撮影の上限（2000 枚）の
  参照を十分に入れられるサイズ。pynetdicom が組み立てる前のサイズは、DTG では
  制限しない（待ち受けは既定でループバックだけ）
- 要求に入れた画像の組（SOP Class UID と SOP Instance UID）だけを見る。
  Referenced SOP Sequence にあれば「確認済」、Failed SOP Sequence にあれば
  「確認の失敗」（Failure Reason の値を記録する）。要求に無い組は捨てる（件数の
  上限の範囲で）。要求したのに結果のどちらにも無い組は「確認の失敗」（理由
  「結果に無い」）にする
- Event Type が 1 でも、Failed SOP Sequence があればその画像は失敗にする
  （記載されているほうを信じる）
- 時間切れにした後に結果が来たら、その結果で置き換える（相手の最後の応答の
  ほうが確か）。ログに「遅れて届いた」と記録する
- 相手から来た値は、ログに `%r` で出力する。画面には件数と状態の言葉だけを表示し、
  相手の文字列は表示しない（Failure Reason は `0x0112` のような値だけ）
- 状態の確認と書き込みは1つのトランザクションで行い、待っている（か時間切れの）
  要求にだけ書き込む。同じ要求に2つの結果が来たら、先に書き込んだほうを残し、
  後のほうには `0x0110` を返す。N-ACTION の失敗も、待っている要求だけを
  「確認の失敗」にする（先に届いた結果を上書きしない）

#### 8.3.3 要求のタイミング・キューの状態

- Web 画面では、保管確認を使う送信先へ1件が送信完了になったら、すぐに N-ACTION を
  送信する（再送で送信できたときも同じ）。画面のプロセスが待ち受けを起動して結果を
  受ける
- CLI では自動で要求しない。`commit --job ID` で要求し、待ち受けを起動して結果か
  時間切れまで待つ（11.8）。画面が同じ待ち受けのポートで動いていれば、CLI は
  待ち受けを起動できないので、その旨を表示して停止する
- 要求するのは状態が送信完了の件だけ。送信できた画像（Success・Warning）の組を、
  送信時に記録した SOP Class UID・SOP Instance UID から集める（ファイルは読み
  直さない）
- キューの各件に、最後の要求の状態を持たせる：「確認待ち・確認済・確認の失敗・
  確認の時間切れ」。保管確認を使わない送信先の件は「—」
- N-ACTION を送信できない（Association を確立できない・相手が Failure を返した）
  ときは「確認の失敗」にし、理由を記録する。自動では再要求しない
  （`commit --job ID` で再要求する。新しい Transaction UID を発行する）
- 時間切れ（送信先の `commitment_timeout_seconds`、既定 600 秒）は、キューを
  読み込むたびに確認して「確認の時間切れ」にする
- 撮影に使った装置プロファイルが `services.storage_commitment: false` なら、
  その撮影の件には要求しない（spec/13 の 8）。撮影の出力フォルダとプロファイルの
  名前の組を状態の保存先に記録して区別する

### 8.4 MPPS

- ワークリストの取得先（または別の MPPS の相手）ごとに、MPPS を使うかを選択する。
  既定は使わない（4.2 のとおり Orthanc は受け付けない）
- 1回の撮影（追加撮影を含む）ごとに、新しい MPPS の SOP Instance を作る。COMPLETED・
  DISCONTINUED を送った MPPS には N-SET を送らない（PS3.4 F.7.2.2.2。6.3）
- 撮影の開始で N-CREATE（IN PROGRESS）、作成の終了で N-SET（COMPLETED）。
  撮影が止まったら N-SET（DISCONTINUED）
- MPPS が失敗しても撮影と送信は止めない。失敗は画面とログに出す

#### 8.4.1 送信先・送信のタイミング・再送

**MPPS は、ワークリストの取得先の `use_mpps: true` のときだけ送信し、送信先は
`modality.mpps:` の相手（設定が無ければワークリストの取得先）にする**
（[ADR-0020](../decisions/0020-mpps-optional-with-retry-queue.md)）。
例外は2つ：CLI の `exam --mpps`・`--no-mpps` はその撮影だけ設定を上書きする。
装置プロファイルが `services.mpps: false` なら、設定で選択していても送信しない
（spec/13 の 8）。

- 撮影の開始は、撮影の値の検証が終わり、画像の作成を始める直前（N-CREATE）。
  作成の終了は画像を書き出し終えた直後（N-SET COMPLETED）
- 撮影が止まったとき（N-CREATE を送信した後、画像の作成の途中のエラー・表現できない
  文字など）は、N-SET（DISCONTINUED）を送信する。画面と CLI には、撮影を取り消す
  操作は無い
- 予約に Study Instance UID が無いときは、N-CREATE より前に DTG が UID を生成し、
  その UID で画像も作成する（MPPS と画像の Study をそろえる）
- MPPS の SOP Instance UID も N-CREATE で決まるので、画像の Referenced Performed
  Procedure Step Sequence にその UID を入れる（6.2 の表。IHE RAD TF-2x A.1.3・
  A.2.2）
- 送信する値は 6.4 のとおり。Performed Series Sequence は作成した画像のヘッダー
  から組み立てる（シリーズごとに Series Instance UID・Series Description・
  Protocol Name と、画像の Referenced SOP Class・Instance UID）
- DISCONTINUED では、停止する前に書き出せた画像も通知する（PS3.4 F.7.2.2.2）。
  読めない画像はスキップする。COMPLETED で画像を読めなければ DISCONTINUED にする
- 送信できない（Association を確立できない・相手が Failure を返した・タイム
  アウト）ときは、その通知を状態の保存先の MPPS のキューに「失敗」で残す。相手の
  Warning は送信成功として扱う
- 再送は `retry.max_attempts`（送信と同じ）の回数だけすぐに試し、それでも失敗した
  ら残す。残った分は CLI の `mpps retry` で再送する（11.9）。順序は必ず N-CREATE が
  先で、N-CREATE が送信できていない件の N-SET は送信せずに待つ
- **送信できたとみなすのは、相手が Success か Warning を返したときだけ。例外は
  2つで、どちらも「前に同じ通知を送信し、応答が無かった」と記録から確認できる
  ときに限る**：
  1. N-CREATE に `0x0111`（同じ SOP Instance が既に存在する）が返り、前の
     N-CREATE が「応答なし」で終わっていた
  2. 終了の N-SET に `0x0110`（完了した MPPS は更新できない。PS3.4 F.7.2.2）が返り、
     前の同じ N-SET が「応答なし」で終わっていた
  - 前に相手が Failure を返していた場合や、前に送信していない場合（N-CREATE を
    待って保留していた N-SET の初回）は、届いていたとは言えないので失敗のまま残す
  - 「応答なし」は、Association を確立して要求を送信した後に、応答が来ないまま
    タイムアウト・切断になったこと。Association を確立できなかった・相手が Failure
    を返した・Presentation Context を拒否されたは「応答なし」に含めない
  - キューの行に、操作ごと（N-CREATE・N-SET）に「応答なしで終わった」フラグを記録する
    （すぐに再送する2回目以降も、このフラグで判定する）
- 再送は、設定の `use_mpps` が false でも、キューに未送信の通知があれば行う
  （`exam --mpps` で作成した分）
- **送信先は行に固定する**：N-CREATE を作成するときの MPPS の相手の AE タイトル・
  ホスト・ポートを行に記録し、再送も必ずその相手へ送信する。設定を後で変えても、
  新しい相手には送信しない。タイムアウトの秒数は現在の設定の値を使う
- **同じ行を2つの処理が同時に送信しない**：送信する前に、行の送信のロックを条件付きの
  更新で取得する（ロックが空か、取得してから 10 分より長く経った行だけ）。取得
  できた処理だけが送信し、終わったらロックを解放する。取得できなかった行は、その回
  は送信せずに残す（`mpps retry` の結果では未送信の件に数える）。画面の撮影・
  複数の CLI の間で有効
- 画像を書き出せなかった（OSError）・作成した画像のヘッダーを読めないときも、
  N-CREATE を送信していれば DISCONTINUED を残す（開いたままにしない）
- MPPS の SOP Instance UID は DTG が生成する（2.25 の UUID の形式）
- 撮影した装置の AE タイトルも行に記録し、再送はその AE タイトルで名乗る（あとで
  装置を切り替えても変えない。ADR-0023）

#### 8.4.2 ローカルでテストする相手

**保管確認の SCP と MPPS の SCP は、テストの中のスタブ（`tests/modality_peers.py`）
としてだけ実装する。DTG の機能として受信側を持たない**
（[ADR-0021](../decisions/0021-test-only-commitment-and-mpps-peers.md)）。
例外は無い。

- 手動でテストするとき：保管確認はテスト用の Orthanc を相手にする
  （[usage.md](../usage.md) の手順）。MPPS は、MPPS を受け付けるテストの相手
  （RIS など）が必要。Orthanc は受け付けない（4.2）

---

## 9. モジュールと配置

### 9.1 規則

**モダリティの通信と手順は `app/modality/` に置き、Service レイヤーの一部として
扱う。** モジュールの依存関係は [architecture.md](../architecture.md) の 2 章の
とおり。例外は2つ。

1. 予約の値から作成の設定への転記（6 章）は、通信が不要な処理なので
   `app/core/worklist_mapping.py` に置く
2. 保管確認の待ち受け（N-EVENT-REPORT を受ける）は SCP の機能だが、SCU の手順の
   一部なので `app/modality/` に置く

### 9.2 外部のパッケージ

`app/modality/` は外部のパッケージ（pynetdicom・pydicom・Pydantic・PyYAML）と
標準ライブラリ（`sqlite3` など）を使う。通信と永続化は `app/core/` へ移さない。

### 9.3 ファイルの配置

```text
app/
├── core/
│   ├── worklist_mapping.py   # 予約 → 作成の設定（Pure）
│   ├── worklist_charset.py   # 画像の文字コードの決定・表現できない文字（Pure）
│   └── models.py             # WorklistItem・ScheduledContext
├── modality/
│   ├── __init__.py
│   ├── config.py             # 自分の AE・相手・送信先（Pydantic）
│   ├── association.py        # Association を確立する共通部分
│   ├── worklist_scu.py       # C-FIND MWL
│   ├── store_scu.py          # C-STORE・C-ECHO
│   ├── commitment_scu.py     # Storage Commitment（N-ACTION・待ち受け・結果の読み取り）
│   ├── mpps_scu.py           # N-CREATE・N-SET（送信する値の組み立てを含む）
│   ├── mpps_queue.py         # MPPS の通知のキュー（sqlite3）
│   ├── queue.py              # 送信キューと履歴・保管確認の要求（sqlite3）
│   └── service.py            # ModalityService（手順をまとめる）
├── web/
│   ├── __init__.py
│   ├── __main__.py           # python -m app.web
│   ├── app.py                # FastAPI のアプリケーション
│   ├── auth.py               # 待ち受けのアドレスと認証
│   ├── routes/               # worklist・exam・pacs・settings
│   ├── templates/            # Jinja2
│   └── static/               # 作成した CSS・htmx・Lucide の SVG
└── cli/
    ├── main.py               # サブコマンドの引数
    └── modality_commands.py  # worklist・exam・send・echo・queue・commit・mpps
```

この図は、モダリティエミュレーターのファイルだけを示す（`app/core/` のほかの
モジュールは spec/02、`app/web/` の詳細は 12a）。

### 9.4 `app/services/` との関係

- `StudyGeneratorService.generate` は、外部から Study Instance UID と予約の値
  （`ScheduledContext`）を受け取れる。渡さなければ、Job からの作成と同じ動作
- 既存の `GenerationConfig` の制約（Patient ID 16 文字・Accession Number
  16 文字など）は予約の値にも適用する。予約の値が制約を超えたら撮影の画面で停止し、
  どの値かを表示する

### 9.5 例外

[08_error_handling.md](08_error_handling.md) の階層に、次がある。

```text
DICOMGeneratorError
└── ModalityError
    ├── ModalityConfigError      # 設定のエラー（ConfigurationError とは別系統）
    ├── AssociationError         # Association を確立できない・拒否された
    ├── WorklistQueryError       # C-FIND の失敗・タイムアウト
    ├── WorklistMappingError     # 予約の値を転記できない（文字・長さ）
    ├── StoreError               # C-STORE の失敗
    ├── StorageCommitmentError   # 保管確認の失敗・タイムアウト
    └── MPPSError                # N-CREATE・N-SET の失敗
```

---

## 12. 設定

`config/app_config.yaml` の `modality:` と `web:` の節に書く。既定のポートは、
保管確認の待ち受けが 11113、Web 画面が 8080。

```yaml
modality:
  stations:                     # 名乗る装置の一覧。画面の情報バーで切り替える
    - name: "CT1"               # 表示名
      ae_title: "DTG_CT01"
      station_name: "DTG_CT01"  # 画像の Station Name。空ならテンプレートなどの値
    - name: "MR1"
      ae_title: "DTG_MR01"
      station_name: "DTG_MR01"
  default_station: "CT1"        # 書かなければ一覧の先頭
  listen:                       # 保管確認の結果を受ける待ち受け
    bind_address: "127.0.0.1"
    port: 11113
  state_dir: "modality_state"   # 予約の最後の結果・送信キュー（sqlite3）
  output_dir: "output/modality"
  character_set: "auto"         # auto, utf8, jis, jis_kana
  character_set_fallback: "utf8"  # utf8, jis, jis_kana（auto は不可）
  default_template: "ct_generic"
  default_profile: null         # 装置プロファイル（spec/13）。null は重ねない
  default_hospital: null        # 病院テンプレート（null で使わない）
  default_pixel_mode: "ct_realistic"  # simple_text, ct_realistic
  worklist:
    ae_title: "RIS_TEST"
    host: "127.0.0.1"
    port: 4242
    timeout_seconds: 30
    query_character_set: "ISO_IR 192"  # 条件に ASCII 以外の文字があるとき
    max_results: 1000             # 応答の上限（5.5）
    max_item_bytes: 262144
    max_total_bytes: 16777216
    use_mpps: false               # MPPS を送信するか（8.4.1）
  mpps: null                      # MPPS の送信先。null はワークリストの取得先
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
      commitment_timeout_seconds: 600  # 保管確認の結果を待つ秒数（8.3）
      commitment_wait_seconds: 0  # 同じ Association で結果を待つ秒数。0 は待たない（8.3.1）
      timeout_seconds: 30         # C-ECHO・C-STORE・N-ACTION のタイムアウト
  default_destination: "PACS_TEST"
  retry:
    max_attempts: 0             # 0 = 自動で再送しない
  max_images_per_exam: 2000     # 1回の撮影の合計の画像数の上限（10.5）
  retake_mode: "append"         # 撮影済みの予約の撮り直し：append・new_order（6.3）
web:
  bind_address: "127.0.0.1"
  port: 8080
```

- 画面は `python -m app.web`（`--config PATH`。既定は `config/app_config.yaml`）で
  起動する。`web:` の節が無ければ上の既定値を使う
- ループバック以外のアドレスで待ち受けるときの認証は 10.9（パスワードは設定
  ファイルに書かず、`DTG_WEB_PASSWORD_FILE` が指すファイルから読む）
- 読み込みは `app/modality/config.py`（Pydantic）。Core からは読まない
- AE タイトルは 16 文字以内で、空白だけのものは禁止する（PS3.5 の AE の VR）
- **装置（`stations`）**（ADR-0023）：表示名・AE タイトル・Station Name を書く。表示名と
  AE タイトルは一覧の中で重複させない。Station Name は SH（16 文字以内・`\` と制御
  文字は不可。PS3.5 6.2）。装置が1台なら、`stations` の代わりに `ae_title`・
  `station_name` だけを書いてもよい（表示名は AE タイトルになる）。両方を書くのは、
  `ae_title`・`station_name` が既定の装置の値と同じときだけ（違えば設定の誤り）
- 画面で選んだ装置は、状態の保存先の `station.json` に表示名で記録する。画面と CLI が
  同じ記録を使い、CLI の `--station <表示名>` はそのコマンドだけに効く（記録は変えない）。
  記録の表示名が設定に無くなっていたら、既定の装置を使い、情報バーで知らせる
- 撮影と送信は、始めたときの装置の AE タイトルで最後まで行う（撮影は装置の値を写して
  から、送信は件に AE タイトルを記録してから進める）。途中で切り替えても名乗りは
  変わらない。画面のプロセスの中で撮影が走っているときと、送信中の件があるときは、
  切り替えを断る（「撮影・送信の最中は装置を切り替えられません」）。別のプロセスの
  CLI で走っている撮影は数えない
- 例はループバックのアドレスと例の名前だけにする。施設の名前・アドレスを書かない
- 設定・状態の保存先のファイル（`worklist_last.json` など）が検証で不正となった
  とき、エラーメッセージは「項目の名前: 原因」だけにし、入っていた値を出さない
  （破損した保存データに患者の氏名が含まれうるため。画面・CLI・ログとも同じ）
- 項目の範囲：`commitment_timeout_seconds` は 1〜86400、`commitment_wait_seconds`
  は 0〜60（同じ Association で長く待たせない）。`mpps:` の AE タイトル・ポートは
  送信先と同じ規則
- 待ち受け（`listen.bind_address`）の既定は `127.0.0.1`。ほかのホストから受ける
  ときだけ設定で変える。待ち受けを起動しただけで、どこからでも Association を
  受け付けることにならないようにするため

---

## 13. ログ

[09_logging.md](09_logging.md) に従う。

- 通信の開始・終了・相手の Status の値・件数を INFO で記録する
- 患者の氏名・生年月日はログに出力しない（[development.md](../development.md) の
  7 章）。出力するのは予約のキー・受付番号・SOP Instance UID まで
- pynetdicom のログは WARNING 以上だけを出力する（既定）。`--verbose` で DEBUG に
  する

---

## 14. 既知の制約

### 14.1 Orthanc の Worklists プラグインと文字コード

`orthancteam/orthanc` の Docker イメージ 26.9.1、Worklists プラグイン 0.9.2 で、
REST でワークリストを作成し、C-FIND MWL（pynetdicom）で取得した結果（2026-10-18 に
測定した）。

| 作成時の SpecificCharacterSet | 作成できたか | 保存された値 | C-FIND の応答 |
|-------------------------------|--------------|--------------|---------------|
| 指定なし（プラグインが ISO_IR 192 にする） | 作成できた | 漢字・かな・英字ともそのまま | ISO_IR 192 で返り、デコードした文字は一致していた（生のバイト列は確認していない） |
| `ISO 2022 IR 87` | 作成できた | **氏名の漢字・かなが消えた**（エラーにならない）。検査の記述も一部だけ残った | 消えたまま返る |
| `ISO 2022 IR 13\ISO 2022 IR 87` | **作成できない**（400 `Unknown encoding while creating DICOM from JSON`） | — | — |

DTG への影響：

- Orthanc の Worklists を相手にするとき、予約は UTF-8 で作成する。DTG は `auto` で
  UTF-8 の画像を作成する。JIS の画像が必要なテストでは、撮影の画面か `--charset` で
  `jis`・`jis_kana` を選択する
- ワークリストの値が既に消えていても、DTG は気付けない（応答は正しい形式で来る）。
  漢字・かなの成分が空の予約を取得したときは、一覧に「漢字・かなが空」の印を
  表示する

### 14.2 Orthanc の文字コードのその他の点

公開の資料から。

- Orthanc は C-FIND の応答（ワークリストを含む）の文字コードに
  `DefaultEncoding` の設定を使う（Orthanc の設定のサンプル `Configuration.json` の
  注記）
- C-FIND の応答で SpecificCharacterSet の複数値を扱えるようになったのは
  1.12.2（Orthanc の `NEWS`）
- ISO_IR 13 のときの円記号（0x5C）と値の区切り `\` の扱いは 1.12.9 で修正された
  （同じ `NEWS`）

### 14.3 DTG の制約

- MPPS は Orthanc を相手に使えない（4.2）
- ワークリストの SCP（RIS の役）は持たない。テストの中だけで起動する
- 画像を受信して保存する Storage SCP は持たない
  （[ADR-0013](../decisions/0013-remove-storage-scp.md)）。保管確認の SCP・
  MPPS の SCP も持たず、テストの中だけで起動する（8.4.2）。ローカルで画像を
  受信したいときは、テスト用の PACS（Orthanc など）を使う
- CLI の `commit` と画面は、同じ待ち受けのポートを同時に使えない（8.3.3）
- 保管確認の時間切れは、キューを読み込んだときに判定する。画面も CLI も動いて
  いない間は「確認待ち」のまま残る
- 異常のデータで UID を壊した画像は、壊れた UID のまま N-ACTION・Performed
  Series Sequence に入れる（相手の拒否の仕方をテストするのに使える）

---

## 15. 出典

2026-10-18 に参照したもの。

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
