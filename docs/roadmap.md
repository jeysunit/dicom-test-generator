# 12b. モダリティのダミー：試験・段・既知の制約・決まったこと・出典

この文書は、モダリティのダミーの**決定の記録・実測・試験の計画・段**を持つ。
現在の仕様は [12_modality_emulator.md](12_modality_emulator.md)、ウェブの画面と
CLI は [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) にある。仕様と
読み比べるのは 12 だけでよい。この文書は、ある決まりが「いつ誰が決めたか」と
「何で確かめたか」を調べるときに読む。

**章の番号は、コード・試験・設定のコメントからの参照を保つため、元の
spec/12 のままにしてある。** この文書は 14〜19 章を持つ。1〜9 章と
12・13 章は spec/12、10・11 章は spec/12a にある。本文の「8.4.2」のような
番号だけの参照は spec/12 の章を指す。

**段の状態は [WORKFLOW.md](../WORKFLOW.md) が唯一の置き場。** この文書の
15 章は、各段の「完了の線」（何をもって完了とするか）だけを持つ。

---

## 14. 試験

**実の PACS・RIS にはつながない。** 試験の中で pynetdicom の SCP を
手元（`127.0.0.1`・空いているポート）に立てて流す。この SCP は
**試験の中の偽の相手**であり、この道具の機能ではない（2026-10-20 に、受信の
機能を外した。[ADR-0013](../adr/0013-remove-storage-scp.md)）。

| 種類 | 置き場 | 中身 |
|------|--------|------|
| Core | `tests/core/test_worklist_mapping.py` | 6 章の表の行ごとに、予約あり・予約なしで写した値を確かめる（生年月日・性別が空の予約、Patient's Size を m のまま写す、予約なしで Request Attributes Sequence・Referenced Study Sequence が無いことを含む）。外の資源を使わない |
| 文字コード | `tests/core/test_worklist_charset.py` | 4つの選択それぞれで、漢字・かな・半角カナの氏名を書き出して読み戻す。表せない字で止まること |
| Modality | `tests/modality/test_worklist_scu.py` | 手元の MWL の SCP（試験の fixture）に C-FIND。条件の組、Pending の打ち切り、時間切れ、文字コードの読み取り |
| Modality | `tests/modality/test_store_scu.py` | 手元の Storage の SCP に C-STORE・C-ECHO。成功・Warning・Failure・つながらない |
| Modality | `tests/modality/test_commitment_scu.py` | 手元の偽の SCP が別の Association で N-EVENT-REPORT を返す形と、同じ Association で返す形。要求→結果→待ち行列の状態の一巡り、一部失敗、時間切れ、遅れて来た結果、相手が落ちている、悪い値（知らない Transaction UID・UID の形でない・知らない Event Type・要求に無い組・別の AE からの結果）（Phase 3c） |
| Modality | `tests/modality/test_mpps_scu.py` | N-CREATE・N-SET の値（予約あり・予約なし）。IN PROGRESS→COMPLETED、撮影が止まったときの DISCONTINUED、相手が落ちていたときに残して `mpps retry` で送る、相手が断る（Failure・Association の拒否）、応答なしの後の `0x0111`・`0x0110` だけを送れた扱いにする（`0x0110` を返し続ける相手・保留の後の N-SET の初回は失敗のまま）、送り先を行に固定する、2つの手順が同時に送り直しても重ねない、プロファイルの `services.mpps: false`（Phase 3c） |
| 統合 | `tests/integration/test_modality_flow.py` | MWL の SCP → `exam --from-worklist --send` → 偽の Storage の SCP（`tests/modality_peers.py`）が受ける。受けた画像の値が予約と合うこと |
| CLI | `tests/cli/test_modality_commands.py` | 各サブコマンドの終了コード・`--json` の形 |
| Web | `tests/web/` | FastAPI の TestClient。頁が開く・HTMX の部分の応答・手元の外で待ち受けて認証が無ければ起動しないこと・`Origin` と CSRF の token の確かめ・相手から来る値（`<script>`・制御文字）がエスケープされること・手元の MWL と Storage の偽の SCP を相手に画面から「取得→選ぶ→撮る→送る」の一巡り |

- MWL の SCP の fixture は、予約を YAML（合成の患者だけ）から作り、
  `EVT_C_FIND` の handler で返す。文字コードを変えた応答も作れる
- ポートは試験ごとに空いているものを取る（固定のポートを使わない）
- 保管の確認の SCP と MPPS の SCP の偽の相手（8.4.2）も
  `tests/modality_peers.py` に置き、結果を返す道（同じ・別の Association）・
  返す Status・返す値を試験ごとに変えられるようにする
- 見た目の値の試験：入力の CSS の `@theme` の値が spec/12a の「10.2」の表と
  同じことを確かめる（`tests/web/test_theme_tokens.py`）

---

## 15. 段（Phase）と完了の線

| 段 | 中身 | 完了の線 |
|----|------|----------|
| **3a** | ワークリスト（C-FIND）・予約からの生成（6 章・7 章）・送信（C-STORE・C-ECHO・待ち行列）を CLI で。Core の写し方、Service の引数の追加、`app/modality/`、例外、設定 | 14 章の Core・文字コード・Modality（worklist・store）・統合・CLI の試験が通る。既存の試験がすべて通る。08・04・WORKFLOW の層の図を更新 |
| **3b** | ウェブの画面（10 章）：ワークリスト・撮影・PACS・設定、見た目の基準、待ち受けと認証 | Web の試験が通る。手元で起動し、手元の MWL の偽の SCP と Storage の偽の SCP を相手に「ワークリストを取得→選ぶ→撮る→送る→確かめる」が画面で通る。CSS を作り直して差が無い |
| **3c** | 保管の確認（N-ACTION・N-EVENT-REPORT・待ち受け）、MPPS（N-CREATE・N-SET）、画面と CLI の `commit`・`--mpps`・`mpps` | Modality（commitment・mpps）の試験が通る。試験用の Orthanc で保管の確認が「確認済」になることを手で確かめ、手順を README に書く（手順は 3c の PR で書いた。**手の確かめは未了**） |

- 3a の前に、この仕様と ADR-0011 の承認を得た（2026-10-18）
- 各段は別の PR（1PR 1目的）。各段で `spec/` の関係する文書を先に直す
- 3c の手の確かめは未了のまま、3c は実装済みとして扱っている。未了の線は
  この表と WORKFLOW の 2 か所だけに書く

---

## 16. 既知の制約

### 16.1 Orthanc の Worklists のプラグインと文字コード（2026-10-18 の実測）

`orthancteam/orthanc` の Docker イメージ 26.9.1、Worklists の
プラグイン 0.9.2 で、REST でワークリストを作り、C-FIND MWL
（pynetdicom）で取得した結果。

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
  正しい形で来る）。漢字・かなの成分が空の予約を取得したときは、
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
- 画像を受け取って保存する Storage SCP は持たない（2026-10-20 に外した。
  ADR-0013）。保管の確認の SCP・MPPS の SCP も持たず、試験の中だけで立てる
  （8.4.2）。手元で画像を受けたいときは、試験用の PACS（Orthanc など）を使う
- CLI の `commit` と画面は、同じ待ち受けのポートを同時に使えない（8.3.3）
- 保管の確認の時間切れは、待ち行列を読んだときに決める。画面も CLI も
  動いていない間は「確認待ち」のまま残る
- 異常のデータで UID を壊した画像は、壊れた UID のまま N-ACTION・
  Performed Series Sequence に入れる（相手の断り方を試すのに使える）

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

## 18. 決まったこと

### 18.0 2026-10-18：画面・技術・包みなど

承認者は、この章の旧版（決めてほしいこと）の8つをすべて推奨のとおりに
決めた。本文の該当の所も、この決まりに合わせてある。

| # | 論点 | 決まったこと | 本文 |
|---|------|--------------|------|
| 1 | この仕様と ADR-0011 | 受け入れた（ADR-0011 は Accepted） | 冒頭・ADR-0011 |
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

- 暗い地で、主の色を文字（リンクなど）に使うときの色。`#1f6feb` は暗い地の上で
  文字には使えない（10.2）。使うときに明るい色を別に決める

### 18.2 2026-10-19：Phase 3c で決めたこと

承認者は 2026-10-19 に Phase 3c に進むことを承認し、次の6つを仕様で
決めて推奨を書くように求めた。Phase 3c の PR（#14）は、どれも推奨のとおりに
作り、マージした。

| # | 論点 | 決まったこと | ほかの案 | 本文 |
|---|------|--------------|----------|------|
| 1 | 保管の確認の結果を受ける道 | 両方で受ける。既定は別の Association（待ち受け）で、N-ACTION の Association はすぐ離す。同じ Association は送り先の `commitment_wait_seconds` に秒を入れたときだけ待つ | 毎回同じ Association で決まった秒だけ待つ（別の道で返す相手のときに毎回待たされる） | 8.3.1 |
| 2 | いつ求めるか | 画面は「送れた」になったらすぐ自動で求める。CLI は `commit --job ID` で求めて待つ（自動にしない） | CLI の `send` でも自動で求めて待つ（`send` が最長 10 分止まる） | 8.3.3・11.8 |
| 3 | 手元で試す受け手 | 試験の中の偽の相手だけ（`tests/modality_peers.py`）。手元の受け取る側には足さない | 手元の受け取る側に保管の確認の SCP と MPPS の SCP の最小の形を足す（受けた画像の台帳・返す先の設定が要る） | 8.4.2 |
| 4 | MPPS の送り先と再送 | `worklist.use_mpps` で使うかを決め、送り先は `modality.mpps:`（無ければワークリストの相手）。送れない知らせは待ち行列に残し、`retry.max_attempts` の分だけすぐ試し、残りは `mpps retry` | 撮影のたびに残りを自動で送り直す（相手が落ちているとき、撮影のたびに時間切れを待つ） | 8.4.1・11.9 |
| 5 | 画面に足す物 | 状態を出すだけ（撮影の頁に MPPS の1行、PACS の頁の待ち行列に「保管の確認」の列）。ボタンは足さない | 求め直す・再送のボタンを画面に足す | 10.5・10.6 |
| 6 | 「取り消し」の意味 | N-CREATE の後に撮影が止まったとき DISCONTINUED を送る（取り消す操作は持たない） | 画面に取り消しのボタンを戻す（Phase 3b で削った） | 8.4.1 |

### 18.3 2026-10-20：受信の機能を外した

承認者の指示（2026-10-20）で、画像を受け取って保存する Storage SCP
（`app/scp/`・CLI の `scp start`・設定の `storage_scp:`・旧 `spec/11`）を
外した。理由は、受信は PACS の役目でモダリティの擬態という目的の外にあり、
試験の相手は使う側が自分で用意すればよいため。原則は「機能は足すより削る」。
記録は [ADR-0013](../adr/0013-remove-storage-scp.md)。

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
