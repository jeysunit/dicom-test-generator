# 13. 装置のプロファイル（Device Profile）

- 作成日：2026-10-18
- 最終更新日：2026-10-22

## 要約

**装置のプロファイルは、ある装置のコンフォーマンスステートメント
（DICOM PS3.2）を読んで、その装置の DICOM の出し方を写した YAML で、
モダリティのテンプレートの上に重ねて使う。** 擬態の仕組み（この文書・
読み込み・検証・重ね方）は公開し、実在の装置の写しは公開しない。
例外は2つある。

1. 公開のリポジトリに置くのは、架空の装置の例
   （`profiles/examples/`）だけ
2. 実在の装置のプロファイルは、リポジトリの外のフォルダに置き、
   設定（`DTG_PROFILE_DIRS`・`profiles.search_paths`）で指して読む

**状態**: 実装済み。未実装は `uid`・`pixel`・`series`・`worklist` の欄と、
CT 以外の SOP Class（「11. 実装の状況」）。

**設計の判断**: [ADR-0012](../decisions/0012-device-profiles.md)・
[ADR-0016](../decisions/0016-generic-template-names.md)（テンプレートの名前）

**関係**: [06_dicom_rules.md](06_dicom_rules.md)（DICOM の規則）・
[07_job_schema.md](07_job_schema.md)（Job YAML の `device_profile`）・
[12_modality_emulator.md](12_modality_emulator.md)（撮るときにプロファイルを選ぶ）

**実装**: `app/core/device_profile.py`（モデルと Dataset への当て方）・
`app/services/profile_loader.py`（置き場と読み込み）・
`profiles/examples/dtg_synthetic_ct.yaml`（架空の装置の例）

---

## 1. 目的と範囲

### 目的

PACS・RIS・ビューアの試験で、**特定の装置が出す形の DICOM** を、
本物の装置を使わずに作る。装置ごとの癖（文字コードの組・必ず出す属性・
空で出す属性・プライベートタグ・Transfer Syntax）は、試験の相手の不具合が
出やすい所で、ここを写せることに価値がある。

### 範囲に入れるもの

- プロファイルの形（スキーマ）・読み込み・検証
- テンプレートとの重ね方
- コンフォーマンスステートメントから写す手順
- 置き場（公開と非公開の分け方）
- CLI（`--profile`・`profiles list`）

### 範囲に入れないもの

- 実在の装置のプロファイルそのもの（公開しない）
- コンフォーマンスステートメントの PDF の自動の読み取り（人が読んで写す）
- 装置の画素の中身の再現（画素は合成のまま。`spec/06` の Pixel Data）

---

## 2. 用語

| 言葉 | 意味 |
|------|------|
| プロファイル | 1台の装置（1つの型名・ソフトウェアの版の組）の出し方を写した YAML |
| テンプレート | `templates/modality/` のモダリティの既定の値（撮影の値・空間・窓） |
| 置き場 | プロファイルを探すフォルダ（「6. 置き場」） |
| 写す | コンフォーマンスステートメントの表の値を、プロファイルの欄に書くこと |
| 合成の根 | DTG の UID の根。`2.25.` で始まる（ADR-0004） |

---

## 3. プロファイルの中身

### 3.1 欄の一覧

「状態」が未実装の欄（`uid`・`pixel`・`series`・`worklist`）は、モデルに欄が
無く、書くと検証の誤りになる（黙って無視しない。`extra="forbid"`）。

| 欄 | 中身 | 写す元（PS3.2 Annex N） | 状態 |
|----|------|------------------------|----|
| `schema_version` | いまは `1` だけ | — | 実装済み |
| `name` | プロファイルの名前。ファイルの名前（拡張子を除く）と同じ | — | 実装済み |
| `description` | 説明 | — | 実装済み |
| `source` | 元になったコンフォーマンスステートメントの題・版・日付・入手先の URL・文書の番号・メモ（分からなければ空） | 表紙（N.0） | 実装済み |
| `device.modality` | Modality (0008,0060)。テンプレートの `info.modality` と同じであること | Table N.9-3 | 実装済み |
| `device.manufacturer` | Manufacturer (0008,0070) | Table N.9-5 | 実装済み |
| `device.manufacturers_model_name` | Manufacturer's Model Name (0008,1090) | Table N.9-5 | 実装済み |
| `device.software_versions` | Software Versions (0018,1020)。複数の値は配列 | Table N.9-5 | 実装済み |
| `device.device_serial_number` | Device Serial Number (0018,1000)。装置の番号の**形**を写した合成の値（実機の番号を書かない） | Table N.9-5 | 実装済み |
| `device.station_name` | Station Name (0008,1010) の既定。病院テンプレートが決めればそちら | Table N.9-5・N.6-1 | 実装済み |
| `device.implementation_version_name` | File Meta の Implementation Version Name (0002,0013) | N.7（Association の表）・N.1 | 実装済み |
| `storage.sop_classes` | 装置が作る（Create）Storage の SOP Class。最初の1つで作る | Table N.1-1 | 実装済み |
| `storage.transfer_syntaxes` | 装置が送れる Transfer Syntax。並びは装置の優先順 | Table N.1-2・N.7-5 | 実装済み |
| `character_set.default` | 装置が既定で出す Specific Character Set (0008,0005) | Table N.1-15・N.5-165 | 実装済み |
| `character_set.supported` | 装置が出せる文字コードの組。空なら確かめない | Table N.1-15 | 実装済み |
| `attributes.set` | 装置が必ず出す属性と値（Presence が ALWAYS・Source が FIXED・CONFIGURATION のもの） | Table N.9-1〜N.9-12・IOD ごとの表 | 実装済み |
| `attributes.empty` | 長さ0で出す属性（Presence・Source が EMPTY） | 同上 | 実装済み |
| `attributes.omit` | 出さない属性（装置の表に無い Type 3） | 同上 | 実装済み |
| `private_tags` | プライベートタグ（群・Private Creator・要素・VR・値） | Table N.9-20・N.9-21（Private Module） | 実装済み |
| `services` | MWL・MPPS・保管確認の対応の有無 | Table N.1-5・N.1.3.5-1〜N.1.3.7-1 | 実装済み。`mpps`・`storage_commitment` は MPPS・保管確認に効く。`modality_worklist` は値を持つだけで、まだ効かない |
| `uid` | UID の形（根の後ろの並び）。根は合成の根だけ | Table N.9-12・N.7 | 未実装 |
| `pixel` | 行列・Bits Allocated/Stored・High Bit・Pixel Representation・Photometric Interpretation | Table N.9-8 | 未実装 |
| `series` | シリーズ・画像の並び方（番号の振り方・Instance Number の始まり） | Table N.9-3・N.9-7 | 未実装 |
| `worklist` | ワークリストから写す項目の違い（写さない・別の属性へ写す） | Table N.5-2・N.5-3 | 未実装 |

### 3.2 例（架空の装置）

```yaml
schema_version: 1
name: dtg_synthetic_ct
description: "架空の CT（仕組みの例）"
source:
  title: ""          # コンフォーマンスステートメントの題
  version: ""        # 版（rev など）
  date: ""           # 発行日（YYYY-MM-DD）
  url: ""            # 入手先
  document_id: ""    # 文書の番号
  notes: "架空。実在の装置の写しではない"
device:
  modality: "CT"
  manufacturer: "DTG Synthetic"
  manufacturers_model_name: "DTG Synthetic CT 64"
  software_versions: ["DTG-CT 2.1.0", "RECON 5.3"]
  device_serial_number: "DTG000123"
  station_name: "DTGCT01"
  implementation_version_name: "DTG_CT_210"
storage:
  sop_classes: ["1.2.840.10008.5.1.4.1.1.2"]
  transfer_syntaxes: ["1.2.840.10008.1.2.1", "1.2.840.10008.1.2"]
character_set:
  default: "ISO 2022 IR 13\\ISO 2022 IR 87"
  supported:
    - "ISO 2022 IR 13\\ISO 2022 IR 87"
    - "ISO_IR 192"
attributes:
  set:
    BodyPartExamined: "CHEST"
  empty: [OperatorsName]
  omit: [SliceLocation]
private_tags:
  - group: "0009"
    creator: "DTG SYNTHETIC CT 01"
    elements:
      - offset: "10"
        vr: "LO"
        value: "SCAN-MODE-A"
        name: "Scan Mode"
services:
  modality_worklist: true
  mpps: false
  storage_commitment: true
```

### 3.3 検証の決まり

読み込みのときに Pydantic で確かめ、誤りはファイルの場所と欄の名前を
添えて止める（`ProfileParseError`。「9. 誤り」）。

- 知らない欄は誤り（綴りの誤りを黙って無視しない）
- `name` は `^[a-z0-9][a-z0-9_]*$`。ファイルの名前と違えば誤り
- UID は DICOM の UID の形（`^[0-2](\.(0|[1-9][0-9]*))+$`、64 文字以内）
- `storage.sop_classes`・`storage.transfer_syntaxes` は1つ以上
- `character_set.default` は `supported` が空でなければ、その中にあること
- `attributes` の名前は DICOM の辞書の Keyword（pydicom の辞書で
  確かめる）。Sequence（SQ）は書けない
- `attributes` で次の属性は触れない（ほかの欄・ほかの仕組みが決める）：
  患者の値（Patient's Name・Patient ID・生年月日・性別・年齢・体重・
  身長）、UID（SOP Class・SOP Instance・Study・Series・Frame of
  Reference）、画素（Pixel Data・Rows・Columns・Bits Allocated・Bits
  Stored・High Bit・Pixel Representation・Samples per Pixel・
  Photometric Interpretation）、Specific Character Set、`device` の欄が
  決める属性（Manufacturer・Manufacturer's Model Name・Software
  Versions・Device Serial Number・Station Name）
- 1つの属性を `set`・`empty`・`omit` の2つ以上に書けば誤り
- `omit` では、DTG が CT Image で出す Type 1・Type 2 の属性
  （Modality・Study Date/Time・Accession Number・Referring Physician's
  Name・Study ID・Series Number・Instance Number・Acquisition Number・
  Content Date/Time・Image Position/Orientation (Patient)・Pixel
  Spacing・Slice Thickness・KVP・Rescale Intercept/Slope・Image Type・
  Patient Position・Position Reference Indicator・Instance Creator UID）
  を消せない（Patient Position は 2C で CT Image Storage では必須。
  PS3.3 C.7.3.1。spec/06 の「CT Image の必須の属性」）。必須の属性を
  欠いた画像は、異常のデータ（`abnormal`）の仕事にする
- `empty` と空の `set`（空の文字列・空の文字列だけの並び）では、DTG が
  CT Image で出す Type 1 の属性（Modality・Image Type・Image
  Position/Orientation (Patient)・Pixel Spacing・Rescale
  Intercept/Slope）を空にできない（PS3.3 C.7.3.1・C.7.6.2・C.8.2.1）
- `attributes.set` と `private_tags` の値は、読み込みのときに VR に
  合うかを確かめる（型・数の範囲・文字の長さと字。pydicom の
  `validate_value`）。文字の VR（DS・IS など）に書いた数は文字にして入れる
- `private_tags` の群は奇数の 4 桁の16進で、`0009`〜`FFFF`
  （`0001`・`0003`・`0005`・`0007` は使えない。PS3.5 7.8.1）。
  `offset` は `10`〜`FF`。1つの群に同じ Creator を2回書かない。
  1つの Creator に同じ `offset` を2回書かない。Creator は 64 文字以内
- `private_tags` の VR は文字と数の VR（AE・AS・CS・DA・DS・DT・IS・
  LO・LT・SH・ST・TM・UC・UI・UR・UT・US・UL・SS・SL・FL・FD）だけ。
  OB・OW・SQ は書けない

---

## 4. テンプレートとの関係

### 4.1 決まり

**プロファイルはテンプレートの上に重ねる（置き換えない）。** 生成には
いままでどおりテンプレート（`modality_template`）を選び、プロファイル
（`device_profile`）は選んだときだけ重ねる。

理由：

- コンフォーマンスステートメントに書いてあるのは「どの属性をどう出すか」
  で、撮影の値（kVp・スライス厚・窓）は書いていない。撮影の値は
  テンプレートが持ち、プロファイルは表に書いてあることだけを持つ。
  プロファイルが小さくなり、写した所と写していない所が分かれる
- 1つのテンプレート（`ct_generic`）に、複数の装置のプロファイルを
  重ねられる
- 置き換えにすると、テンプレートの欄（`ct_image`・`spatial`・
  `window_presets`）をプロファイルごとに写すことになり、写し忘れが
  黙って既定の値になる

### 4.2 重ねる順

値が重なったときは、下の行が勝つ。

| 順 | 置き場 | 決めるもの |
|----|--------|------------|
| 1 | Job YAML | `character_set`・`transfer_syntax` など |
| 2 | モダリティのテンプレート | 撮影の値・既定の装置の値・`character_set` |
| 3 | 装置のプロファイル | 装置の値・文字コードの既定・属性の出し方・プライベートタグ |
| 4 | 病院テンプレート（`overrides`） | 施設の名前・Station Name・文字コード |

例外は2つある。

1. **装置の値（Manufacturer・Manufacturer's Model Name・Software
   Versions・Device Serial Number・Implementation Version Name・作る
   SOP Class）は、病院テンプレートでも変えない。** 施設は装置を
   作り替えられない
2. **`attributes`（set・empty・omit）とプライベートタグは、最後に
   当てる。** 装置の表のとおりに出すため

### 4.3 合わないときは止める

次のときは生成を始めずに `ProfileMismatchError` で止める（黙って
直さない）。

- `device.modality` とテンプレートの `info.modality` が違う
- Job の `transfer_syntax.uid` が `storage.transfer_syntaxes` に無い
  （`quick` はプロファイルの最初の形を使う）
- 重ねた後の文字コードが `character_set.supported` に無い
  （`supported` が空なら確かめない）
- `storage.sop_classes` の最初の SOP Class を、DTG がまだ作れない
  （今作れるのは CT Image Storage だけ）

文字コードの比べ方：値を `\` で分け、前後の空白を除く。値 1 が空なら
`ISO 2022 IR 6` とみなす（PS3.3 C.12.1.1.2）。値が無い（空・属性なし）
ときは既定の文字セット `ISO_IR 6` とみなす。

---

## 5. コンフォーマンスステートメントから写す手順

PS3.2 の Annex N（Conformance Statement Template）の形の文書を前提に
する。古い形（Annex A。2022d まで）の文書は、同じ名前の表を探す。

1. **表紙（N.0）**：題・版・日付・文書の番号を `source` に写す。
   入手先の URL も写す（分からなければ空）
2. **Table N.1-1 Storage SOP Classes**：「Create」の列に印のある SOP
   Class を `storage.sop_classes` に写す。装置が主に作る画像を最初に置く
3. **Table N.1-2 Supported Transfer Syntaxes と Table N.7-5（Transfer
   Syntax の優先順）**：送る役（SCU）の Transfer Syntax を、優先順に
   `storage.transfer_syntaxes` に写す
4. **Table N.1-15 Supported Specific Character Sets**：出せる組を
   `character_set.supported` に写す。装置が既定で出す組（N.6-1 の設定の
   表や N.5-165 の注に書いてあることが多い）を `default` に写す
5. **Table N.1-5・N.1.3.5-1・N.1.3.6-1・N.1.3.7-1**：MWL・保管確認・
   MPPS の対応の有無を `services` に写す
6. **N.9 IOD の表（Table N.9-1〜N.9-12、IOD ごとの表）**：
   Presence と Source の列で分ける

   | 表の値 | プロファイルの欄 |
   |--------|------------------|
   | Presence が ALWAYS、Source が FIXED | `attributes.set` に値を写す |
   | Presence が ALWAYS、Source が CONFIGURATION | `attributes.set` に、合成の値で形を写す |
   | Presence か Source が EMPTY | `attributes.empty` |
   | Source が GENERATED・MWL・USER・QUERY・SCANNED | 写さない（DTG が作るか、予約から写す） |
   | テンプレートが出すが、装置の表に無い Type 3 | `attributes.omit` |

   General Equipment（Table N.9-5）の Manufacturer・型名・
   ソフトウェアの版・装置の番号・Station Name は `device` に写す
7. **Table N.9-20・N.9-21（Private Module）**：Private Creator・群・
   要素・VR・値を `private_tags` に写す。値が装置ごとに変わるもの
   （番号・日時）は、形だけを写した合成の値にする
8. **Table N.9-8 Image Pixel・Table N.9-12 SOP Common**：未実装の欄
   （`pixel`・`uid`）のために書き留める。今は写さない
9. **Table N.5-2・N.5-3（MWL の問い合わせと返す値）**：未実装の欄
   （`worklist`）のために書き留める

写した後、`python -m app.cli profiles list` で読めることを確かめ、
`generate --profile` で作った画像を、文書の表と並べて確かめる。

### 5.1 写さないもの

例外を含めて3つの決まりがある。

1. **実在の会社の UID の根を使わない。** 装置の UID の形（根の後ろの
   並び）は未実装の `uid` の欄で、合成の根（`2.25.` で始まる）の後ろに作る
2. **実機の番号（装置の番号・施設の名前・AE タイトル）を写さない。**
   形（桁の数・文字の種類）だけを写した合成の値にする
3. **患者の値を写さない。** 例に出ている値も写さない

---

## 6. 置き場

### 6.1 決まり

**公開のリポジトリには架空の装置の例だけを置き、実在の装置の
プロファイルは外のフォルダに置く。** 探す順は次のとおり。

| 順 | 置き場 | 指し方 |
|----|--------|--------|
| 1 | 環境の変数 `DTG_PROFILE_DIRS` | フォルダを OS のパスの区切り（Linux・macOS は `:`、Windows は `;`）で並べる |
| 2 | 設定のファイルの `profiles.search_paths` | `config/app_config.yaml`。相対のパスは設定のファイルの場所から |
| 3 | リポジトリの `profiles/examples/` | 架空の装置の例 |

```yaml
# config/app_config.yaml
profiles:
  search_paths: []   # 例: ["~/dtg-private-profiles"]
```

- 各フォルダの直下の `*.yaml` を読む（下のフォルダは探さない）
- `~` はホームディレクトリに展開する
- 指したフォルダが無ければ誤り（`ProfileError`）。綴りの誤りで、
  黙って例のプロファイルに落ちないため。確かめるのはプロファイルを
  使うとき・一覧を出すときだけ（プロファイルを使わない生成は止めない）
- 設定の `profiles` が対応表でない、知らない鍵がある、`search_paths` が
  文字の並びでないときも誤り（黙って例の置き場だけにしない）
- プロファイルのファイルは UTF-8。読めなければ `ProfileParseError`
- **同じ名前のプロファイルが2か所以上にあれば誤り**
  （`DuplicateProfileError`。どちらのパスかを出す）。上の置き場が
  黙って下を隠すと、どちらで作ったかが分からなくなるため

### 6.2 誤って公開に入らない形

- `.gitignore` で `profiles/` の下を `examples/` 以外すべて外す
  （`profiles/private/` に置いても git に乗らない）
- 試験（`tests/services/test_profile_loader.py`）で、リポジトリの
  `profiles/` の下に `examples/` 以外の YAML が無いこと、例の
  `device.manufacturer` が `DTG` で始まることを確かめる
- 実在の装置のプロファイルは、利用者の非公開の保存の場所（非公開の
  リポジトリなど）で持つ

### 6.3 テンプレートの名前の決まりとの関係

公開のテンプレートに商用の製品の名前を使わない決まり
（[ADR-0016](../decisions/0016-generic-template-names.md)）は、公開の置き場の
**例のプロファイル**にも当てる。外の置き場のプロファイルには当てない
（名前・中身に実在の装置の名前を書いてよい）。

---

## 7. Job YAML と CLI

### 7.1 Job YAML

```yaml
modality_template: "ct_generic"
device_profile: "dtg_synthetic_ct"   # 省略可。省略すればいまと同じ
```

### 7.2 CLI

```bash
# Job YAML の device_profile を上書き
python -m app.cli generate job.yaml --profile dtg_synthetic_ct

# quick で選ぶ
python -m app.cli quick -p P000001 -m ct_generic --profile dtg_synthetic_ct \
  -s 1 -i 3 -o output/

# 読めるプロファイルの一覧（名前・モダリティ・製造者・型名・置き場）
python -m app.cli profiles list
```

- `profiles list` は、壊れたプロファイルがあっても止まらずに一覧を
  出し、壊れたものは理由を添えて標準エラーに出す。終了コードは、
  1つでも壊れていれば 2（設定のエラー）
- 終了コードは [04_cli.md](04_cli.md) のとおり。プロファイルの誤りは 2

### 7.3 古い名前のテンプレート

以前の、実在の装置の名前のテンプレートを `-m`・`modality_template` で
読みに来たら、`TemplateNotFoundError` に「装置ごとの写しはプロファイルに
なった。外の置き場に置き、`--profile` で選ぶ」という案内（`hint`）を添える。
古い名前は、名前そのものでなく SHA-256 の値でコードに持つ
（`app/services/template_loader.py`。ADR-0016）。

---

## 8. モダリティエミュレーター（spec/12）との関係

- 撮るときにプロファイルを選べる：設定 `modality.default_profile`
  （既定は無し）、撮影の画面の「装置」、CLI `exam --profile`
- プロファイルの `device.modality` と予約のモダリティが違えば、
  テンプレートと同じく撮影の画面で止める
  （[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の 10.5）
- `services.mpps`・`services.storage_commitment` が `false` の
  プロファイルでは、設定で選んでも MPPS・保管確認を送らない
  （装置が対応しない動きを作らない。`app/modality/service.py` の
  `_profile_supports`・`_profile_allows`）
- `worklist` の欄（予約から写す項目の違いを、
  [12_modality_emulator.md](12_modality_emulator.md) の 6 章の表の上に重ねる）は
  **未実装**。いまの写し方は 6 章の表のまま、プロファイルでは変えられない

---

## 9. 誤り

`app/core/exceptions.py` にあり、[08_error_handling.md](08_error_handling.md) の階層に載せてある。
どれも `ConfigurationError` の下で、CLI の終了コードは 2。

```text
ConfigurationError
└── ProfileError                 # 置き場の誤り（無いフォルダ）など
    ├── ProfileNotFoundError     # 名前が見つからない（探した置き場を添える）
    ├── ProfileParseError        # YAML の誤り・スキーマの誤り（ファイルと欄を添える）
    ├── DuplicateProfileError    # 同じ名前が2か所以上
    └── ProfileMismatchError     # テンプレート・Job と合わない（4.3）
```

誤りの文の例：

```text
Invalid device profile: /path/to/x.yaml
  (errors=device.manufacturer: Field required; private_tags.0.group: ...)
Device profile not found: abc (searched=/a, /b, /repo/profiles/examples)
```

---

## 10. 試験

| 置き場 | 中身 |
|--------|------|
| `tests/core/test_device_profile.py` | モデルの検証（知らない欄・名前・UID・群・offset・VR・触れない属性・重なり）。Dataset に当てた結果（装置の値・属性・プライベートタグ） |
| `tests/services/test_profile_loader.py` | 外のフォルダから読める・探す順・同じ名前の誤り・無いフォルダの誤り・壊れた YAML の誤り・リポジトリに例しか無いこと |
| `tests/services/test_study_generator_profile.py` | 架空のプロファイルで作った画像に、製造者・型名・ソフトウェアの版・プライベートタグ・文字コード（IR 13＋IR 87 の漢字の氏名を読み戻す）が入ること。合わないときに止まること |
| `tests/cli/test_profile_commands.py` | `--profile`・`profiles list`・誤りの終了コード 2・古い名前の案内 |

---

## 11. 実装の状況

| 機能 | 状態 |
|------|------|
| モデル・読み込み・検証・重ね方（装置の値・Transfer Syntax・文字コード・属性・プライベートタグ）・CLI | 実装済み（10 章の試験） |
| `exam --profile`・`modality.default_profile`・撮影の画面の「装置」 | 実装済み |
| `services.mpps`・`services.storage_commitment` を MPPS・保管確認に反映する（[12_modality_emulator.md](12_modality_emulator.md) の 8.3.3・8.4.1） | 実装済み。`services.modality_worklist` は反映しない |
| `uid`・`pixel`・`series` の欄。CT 以外の SOP Class | 未実装。モデルに欄が無く、作れる SOP Class は CT Image Storage だけ |
| `worklist` の欄 | 未実装 |

未実装のものは [roadmap.md](../roadmap.md) にもある。

---

## 12. 出典

2026-10-18 に読んだもの。

- DICOM PS3.2 2026d Annex N「DICOM Conformance Statement Template
  (Normative)」：N.1（Table N.1-1・N.1-2・N.1-5・N.1-15）、N.5、
  N.6、N.7（Table N.7-5）、N.9（Source と Presence の値、
  Table N.9-1〜N.9-21）
- DICOM PS3.2 2026d Annex A（古い形。いまは Retired で、2022d を指す）
- DICOM PS3.5 7.8（Private Data Elements）
- DICOM PS3.3 C.12.1.1.2（Specific Character Set）
