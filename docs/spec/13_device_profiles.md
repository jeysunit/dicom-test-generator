# 13. 装置プロファイル（Device Profile）

## 要約

**装置プロファイルは、ある装置のコンフォーマンスステートメント（DICOM PS3.2）を
読み、その装置の DICOM の出力方法を転記した YAML で、モダリティテンプレートの
上に重ねて使う。** 再現の仕組み（この文書・読み込み・検証・重ね方）は公開し、
実在の装置のプロファイルは公開しない。例外は2つある。

1. 公開のリポジトリに置くのは、架空の装置の例（`profiles/examples/`）だけ
2. 実在の装置のプロファイルは、リポジトリの外のフォルダに置き、設定
   （`DTG_PROFILE_DIRS`・`profiles.search_paths`）で指定して読み込む

**状態**: 実装済み。未実装は `uid`・`pixel`・`series`・`worklist` のフィールドと、
CT 以外の SOP Class（「11. 実装の状況」）。

**設計の判断**: [ADR-0012](../decisions/0012-device-profiles.md)・
[ADR-0016](../decisions/0016-generic-template-names.md)（テンプレートの名前）

**関係**: [06_dicom_rules.md](06_dicom_rules.md)（DICOM の規則）・
[07_job_schema.md](07_job_schema.md)（Job YAML の `device_profile`）・
[12_modality_emulator.md](12_modality_emulator.md)（撮影時にプロファイルを選択する）

**実装**: `app/core/device_profile.py`（モデルと Dataset への適用）・
`app/services/profile_loader.py`（配置場所と読み込み）・
`profiles/examples/dtg_synthetic_ct.yaml`（架空の装置の例）

---

## 1. 目的と範囲

### 目的

PACS・RIS・ビューアのテストで、**特定の装置が出力する形の DICOM** を、本物の
装置を使わずに作成する。装置ごとの特徴（文字コードの組み合わせ・必ず出力する属性・
空で出力する属性・プライベートタグ・Transfer Syntax）は、テスト対象の不具合が
出やすい部分で、ここを再現できることに価値がある。

### 範囲に入れるもの

- プロファイルの形式（スキーマ）・読み込み・検証
- テンプレートとの重ね方
- コンフォーマンスステートメントから転記する手順
- 配置場所（公開と非公開の分け方）
- CLI（`--profile`・`profiles list`）

### 範囲に入れないもの

- 実在の装置のプロファイルそのもの（公開しない）
- コンフォーマンスステートメントの PDF の自動読み取り（人が読んで転記する）
- 装置の画素の内容の再現（画素は合成のまま。`spec/06` の Pixel Data）

---

## 2. 用語

| 用語 | 意味 |
|------|------|
| プロファイル | 1台の装置（1つの型名・ソフトウェアバージョンの組み合わせ）の出力方法を転記した YAML |
| テンプレート | `templates/modality/` のモダリティの既定値（撮影の値・空間・ウィンドウ） |
| 配置場所 | プロファイルを探すフォルダ（「6. 配置場所」） |
| 転記 | コンフォーマンスステートメントの表の値を、プロファイルのフィールドに書くこと |
| 合成のルート | DTG の UID のルート。`2.25.` で始まる（ADR-0004） |

---

## 3. プロファイルの内容

### 3.1 フィールドの一覧

「状態」が未実装のフィールド（`uid`・`pixel`・`series`・`worklist`）は、モデルに
フィールドが無く、書くと検証エラーになる（黙って無視しない。`extra="forbid"`）。

| フィールド | 内容 | 転記元（PS3.2 Annex N） | 状態 |
|------------|------|------------------------|------|
| `schema_version` | 現在は `1` だけ | — | 実装済み |
| `name` | プロファイルの名前。ファイル名（拡張子を除く）と同じ | — | 実装済み |
| `description` | 説明 | — | 実装済み |
| `source` | 転記元のコンフォーマンスステートメントのタイトル・版・日付・入手先の URL・文書番号・メモ（不明なら空） | 表紙（N.0） | 実装済み |
| `device.modality` | Modality (0008,0060)。テンプレートの `info.modality` と同じであること | Table N.9-3 | 実装済み |
| `device.manufacturer` | Manufacturer (0008,0070) | Table N.9-5 | 実装済み |
| `device.manufacturers_model_name` | Manufacturer's Model Name (0008,1090) | Table N.9-5 | 実装済み |
| `device.software_versions` | Software Versions (0018,1020)。複数の値は配列 | Table N.9-5 | 実装済み |
| `device.device_serial_number` | Device Serial Number (0018,1000)。装置番号の**形式**だけを転記した合成の値（実機の番号を書かない） | Table N.9-5 | 実装済み |
| `device.station_name` | Station Name (0008,1010) の既定値。病院テンプレートが指定すればそちら。モダリティエミュレーターで選んだ装置に Station Name があれば、それが先（spec/12 の 6.2・ADR-0023） | Table N.9-5・N.6-1 | 実装済み |
| `device.implementation_version_name` | File Meta の Implementation Version Name (0002,0013) | N.7（Association の表）・N.1 | 実装済み |
| `storage.sop_classes` | 装置が作成する（Create）Storage の SOP Class。最初の1つで作成する | Table N.1-1 | 実装済み |
| `storage.transfer_syntaxes` | 装置が送信できる Transfer Syntax。並びは装置の優先順 | Table N.1-2・N.7-5 | 実装済み |
| `character_set.default` | 装置がデフォルトで出力する Specific Character Set (0008,0005) | Table N.1-15・N.5-165 | 実装済み |
| `character_set.supported` | 装置が出力できる文字コードの組み合わせ。空なら検証しない | Table N.1-15 | 実装済み |
| `attributes.set` | 装置が必ず出力する属性と値（Presence が ALWAYS・Source が FIXED・CONFIGURATION のもの） | Table N.9-1〜N.9-12・IOD ごとの表 | 実装済み |
| `attributes.empty` | 長さ0で出力する属性（Presence・Source が EMPTY） | 同上 | 実装済み |
| `attributes.omit` | 出力しない属性（装置の表に無い Type 3） | 同上 | 実装済み |
| `private_tags` | プライベートタグ（グループ・Private Creator・要素・VR・値） | Table N.9-20・N.9-21（Private Module） | 実装済み |
| `services` | MWL・MPPS・保管確認（Storage Commitment）の対応の有無 | Table N.1-5・N.1.3.5-1〜N.1.3.7-1 | 実装済み。`mpps`・`storage_commitment` は MPPS・保管確認に反映される。`modality_worklist` は値を持つだけで、まだ反映されない |
| `uid` | UID の形式（ルートの後ろの並び）。ルートは合成のルートだけ | Table N.9-12・N.7 | 未実装 |
| `pixel` | マトリクス・Bits Allocated/Stored・High Bit・Pixel Representation・Photometric Interpretation | Table N.9-8 | 未実装 |
| `series` | シリーズ・画像の並び方（番号の振り方・Instance Number の開始値） | Table N.9-3・N.9-7 | 未実装 |
| `worklist` | ワークリストから転記する項目の違い（転記しない・別の属性へ転記する） | Table N.5-2・N.5-3 | 未実装 |

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
  document_id: ""    # 文書番号
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

### 3.3 検証の規則

読み込み時に Pydantic で検証し、エラーはファイルの場所とフィールド名を添えて停止
する（`ProfileParseError`。「9. エラー」）。

- 未知のフィールドはエラー（綴りの誤りを黙って無視しない）
- `name` は `^[a-z0-9][a-z0-9_]*$`。ファイル名と異なればエラー
- UID は DICOM の UID の形式（`^[0-2](\.(0|[1-9][0-9]*))+$`、64 文字以内）
- `storage.sop_classes`・`storage.transfer_syntaxes` は1つ以上
- `character_set.default` は、`supported` が空でなければ、その中にあること
- `attributes` の名前は DICOM の辞書の Keyword（pydicom の辞書で検証する）。
  Sequence（SQ）は書けない
- `attributes` で次の属性は扱えない（ほかのフィールド・ほかの仕組みが決める）：
  患者の値（Patient's Name・Patient ID・生年月日・性別・年齢・体重・身長）、
  UID（SOP Class・SOP Instance・Study・Series・Frame of Reference）、画素
  （Pixel Data・Rows・Columns・Bits Allocated・Bits Stored・High Bit・Pixel
  Representation・Samples per Pixel・Photometric Interpretation）、Specific
  Character Set、`device` のフィールドが決める属性（Manufacturer・Manufacturer's
  Model Name・Software Versions・Device Serial Number・Station Name）、
  Modality（`device.modality` が決める。`set` で別の値にも、`empty` で空にも
  できない）
- 1つの属性を `set`・`empty`・`omit` の2つ以上に書けばエラー
- `omit` では、DTG が CT Image で出力する Type 1・Type 2 の属性
  （Modality・Study Date/Time・Accession Number・Referring Physician's
  Name・Study ID・Series Number・Instance Number・Acquisition Number・
  Content Date/Time・Image Position/Orientation (Patient)・Pixel
  Spacing・Slice Thickness・KVP・Rescale Intercept/Slope・Image Type・
  Patient Position・Position Reference Indicator・Instance Creator UID、
  MR の Scanning Sequence・Sequence Variant・Scan Options・MR Acquisition
  Type・Repetition Time・Inversion Time・Echo Time・Echo Train Length）
  を削除できない（Patient Position は 2C で CT Image Storage では必須。
  PS3.3 C.7.3.1。spec/06 の「CT Image の必須の属性」）。必須の属性を欠いた
  画像は、異常のデータ（`abnormal`）で作成する
- `empty` と空の `set`（空文字列・空文字列だけの並び）では、DTG が CT Image で
  出力する Type 1 の属性（Image Type・Image Position/Orientation
  (Patient)・Pixel Spacing・Rescale Intercept/Slope、MR の Scanning
  Sequence・Sequence Variant）を空にできない
  （PS3.3 C.7.3.1・C.7.6.2・C.8.2.1）
- `set` では、上の Type 1 の属性に規格に合わない値を書けない（読み込みの誤りに
  なる。PS3.3 C.7.6.2・C.8.2.1・C.8.2.1.1.1）。Image Type は 2 値以上で、
  値 1 が `ORIGINAL` か `DERIVED`。Image Position (Patient) は 3 値、Image
  Orientation (Patient) は 6 値、Pixel Spacing は 2 値、Rescale Intercept と
  Rescale Slope は 1 値で、数であること。Rescale Slope は 0 にできない。意図して
  壊した画像は、異常のデータ（`abnormal`）で作成する
- `attributes.set` と `private_tags` の値は、読み込み時に VR に合うかを検証する
  （型・数値の範囲・文字列の長さと文字。pydicom の `validate_value`）。文字列の
  VR（DS・IS など）に書いた数値は文字列にして入れる
- `private_tags` のグループは奇数の 4 桁の16進数で、`0009`〜`FFFF`
  （`0001`・`0003`・`0005`・`0007` は使えない。PS3.5 7.8.1）。`offset` は
  `10`〜`FF`。1つのグループに同じ Creator を2回書かない。1つの Creator に同じ
  `offset` を2回書かない。Creator は 64 文字以内
- `private_tags` の VR は文字列と数値の VR（AE・AS・CS・DA・DS・DT・IS・
  LO・LT・SH・ST・TM・UC・UI・UR・UT・US・UL・SS・SL・FL・FD）だけ。
  OB・OW・SQ は書けない

---

## 4. テンプレートとの関係

### 4.1 規則

**プロファイルはテンプレートの上に重ねる（置き換えない）。** 作成には従来どおり
テンプレート（`modality_template`）を選択し、プロファイル（`device_profile`）は
選択したときだけ重ねる。

理由：

- コンフォーマンスステートメントに書いてあるのは「どの属性をどう出力するか」で、
  撮影の値（kVp・スライス厚・ウィンドウ）は書いていない。撮影の値はテンプレートが
  持ち、プロファイルは表に書いてあることだけを持つ。プロファイルが小さくなり、
  転記した部分と転記していない部分が分かれる
- 1つのテンプレート（`ct_generic`）に、複数の装置のプロファイルを重ねられる
- 置き換えにすると、テンプレートのフィールド（`ct_image`・`spatial`・
  `window_presets`）をプロファイルごとに転記することになり、転記漏れが黙って
  既定値になる

### 4.2 重ねる順序

値が重なったときは、下の行が優先される。

| 順 | 配置場所 | 決めるもの |
|----|----------|------------|
| 1 | Job YAML | `character_set`・`transfer_syntax` など |
| 2 | モダリティテンプレート | 撮影の値・既定の装置の値・`character_set` |
| 3 | 装置プロファイル | 装置の値・文字コードの既定値・属性の出力方法・プライベートタグ |
| 4 | 病院テンプレート（`overrides`） | 施設の名前・Station Name・文字コード |

例外は2つある。

1. **装置の値（Manufacturer・Manufacturer's Model Name・Software
   Versions・Device Serial Number・Implementation Version Name・作成する
   SOP Class）は、病院テンプレートでも変えない。** 施設は装置を変更できない
2. **`attributes`（set・empty・omit）とプライベートタグは、最後に適用する。**
   装置の表のとおりに出力するため

### 4.3 合わないときは停止する

次のときは作成を始めずに `ProfileMismatchError` で停止する（黙って修正しない）。

- `device.modality` とテンプレートの `info.modality` が異なる
- Job の `transfer_syntax.uid` が `storage.transfer_syntaxes` に無い
  （`quick` はプロファイルの最初の Transfer Syntax を使う）
- 重ねた後の文字コードが `character_set.supported` に無い
  （`supported` が空なら検証しない）
- `storage.sop_classes` の最初の SOP Class を、DTG がまだ作成できない
  （現在作成できるのは CT Image Storage と MR Image Storage。
  [ADR-0028](../decisions/0028-mr-images.md)）

文字コードの比較方法：値を `\` で分け、前後の空白を除く。値 1 が空なら
`ISO 2022 IR 6` とみなす（PS3.3 C.12.1.1.2）。値が無い（空・属性なし）ときは
デフォルトの文字セット `ISO_IR 6` とみなす。

---

## 5. コンフォーマンスステートメントから転記する手順

PS3.2 の Annex N（Conformance Statement Template）の形式の文書を前提にする。
古い形式（Annex A。2022d まで）の文書は、同じ名前の表を探す。

1. **表紙（N.0）**：タイトル・版・日付・文書番号を `source` に転記する。入手先の URL も
   転記する（不明なら空）
2. **Table N.1-1 Storage SOP Classes**：「Create」の列に印のある SOP Class を
   `storage.sop_classes` に転記する。装置が主に作成する画像を最初に置く
3. **Table N.1-2 Supported Transfer Syntaxes と Table N.7-5（Transfer Syntax の
   優先順）**：送信側（SCU）の Transfer Syntax を、優先順に
   `storage.transfer_syntaxes` に転記する
4. **Table N.1-15 Supported Specific Character Sets**：出力できる組み合わせを
   `character_set.supported` に転記する。装置がデフォルトで出力する組み合わせ
   （N.6-1 の設定の表や N.5-165 の注に書いてあることが多い）を `default` に転記
   する
5. **Table N.1-5・N.1.3.5-1・N.1.3.6-1・N.1.3.7-1**：MWL・保管確認・MPPS の対応の
   有無を `services` に転記する
6. **N.9 IOD の表（Table N.9-1〜N.9-12、IOD ごとの表）**：Presence と Source の
   列で分ける

   | 表の値 | プロファイルのフィールド |
   |--------|--------------------------|
   | Presence が ALWAYS、Source が FIXED | `attributes.set` に値を転記する |
   | Presence が ALWAYS、Source が CONFIGURATION | `attributes.set` に、形式だけを転記した合成の値を書く |
   | Presence か Source が EMPTY | `attributes.empty` |
   | Source が GENERATED・MWL・USER・QUERY・SCANNED | 転記しない（DTG が作成するか、予約から転記する） |
   | テンプレートが出力するが、装置の表に無い Type 3 | `attributes.omit` |

   General Equipment（Table N.9-5）の Manufacturer・型名・ソフトウェアバージョン・
   装置番号・Station Name は `device` に転記する
7. **Table N.9-20・N.9-21（Private Module）**：Private Creator・グループ・要素・
   VR・値を `private_tags` に転記する。値が装置ごとに変わるもの（番号・日時）は、
   形式だけを転記した合成の値にする
8. **Table N.9-8 Image Pixel・Table N.9-12 SOP Common**：未実装のフィールド
   （`pixel`・`uid`）のために控えておく。現在は転記しない
9. **Table N.5-2・N.5-3（MWL の問い合わせと返却する値）**：未実装のフィールド
   （`worklist`）のために控えておく

転記した後、`python -m app.cli profiles list` で読み込めることを確認し、
`generate --profile` で作成した画像を、文書の表と並べて確認する。

### 5.1 転記しないもの

例外を含めて3つの規則がある。

1. **実在の会社の UID のルートを使わない。** 装置の UID の形式（ルートの後ろの
   並び）は未実装の `uid` フィールドで、合成のルート（`2.25.` で始まる）の後ろに
   生成する
2. **実機の番号（装置番号・施設の名前・AE タイトル）を転記しない。** 形式
   （桁数・文字の種類）だけを転記した合成の値にする
3. **患者の値を転記しない。** 例に記載されている値も転記しない

---

## 6. 配置場所

### 6.1 規則

**公開のリポジトリには架空の装置の例だけを置き、実在の装置のプロファイルは外部の
フォルダに置く。** 検索の順序は次のとおり。

| 順 | 配置場所 | 指定方法 |
|----|----------|----------|
| 1 | 環境変数 `DTG_PROFILE_DIRS` | フォルダを OS のパスの区切り文字（Linux・macOS は `:`、Windows は `;`）で並べる |
| 2 | 設定ファイルの `profiles.search_paths` | `config/app_config.yaml`。相対パスは設定ファイルの場所を基準にする |
| 3 | リポジトリの `profiles/examples/` | 架空の装置の例 |

```yaml
# config/app_config.yaml
profiles:
  search_paths: []   # 例: ["~/dtg-private-profiles"]
```

- 各フォルダの直下の `*.yaml` を読み込む（サブフォルダは検索しない）
- `~` はホームディレクトリに展開する
- 指定したフォルダが無ければエラー（`ProfileError`）。綴りの誤りのせいで、黙って
  例のプロファイルが使われることを防ぐため。検証するのはプロファイルを使うとき・
  一覧を出力するときだけ（プロファイルを使わない作成は止めない）
- 設定の `profiles` がマッピングでない、未知のキーがある、`search_paths` が
  文字列のリストでないときもエラー（黙って例の配置場所だけにしない）
- プロファイルのファイルは UTF-8。読めなければ `ProfileParseError`
- **同じ名前のプロファイルが2か所以上にあればエラー**
  （`DuplicateProfileError`。どちらのパスかを表示する）。上位の配置場所が黙って
  下位を隠すと、どちらで作成したかが分からなくなるため

### 6.2 誤って公開されないための仕組み

- `.gitignore` で `profiles/` の下を `examples/` 以外すべて除外する
  （`profiles/private/` に置いても Git で追跡されない）
- テスト（`tests/services/test_profile_loader.py`）で、リポジトリの `profiles/`
  の下に `examples/` 以外の YAML が無いこと、例の `device.manufacturer` が `DTG` で
  始まることを確認する
- 実在の装置のプロファイルは、利用者の非公開の保存場所（非公開のリポジトリなど）で
  管理する

### 6.3 テンプレートの命名規則との関係

公開のテンプレートに商用製品の名前を使わない規則
（[ADR-0016](../decisions/0016-generic-template-names.md)）は、公開の配置場所の
**例のプロファイル**にも適用する。外部の配置場所のプロファイルには適用しない
（名前・内容に実在の装置の名前を書いてよい）。

---

## 7. Job YAML と CLI

### 7.1 Job YAML

```yaml
modality_template: "ct_generic"
device_profile: "dtg_synthetic_ct"   # 省略可。省略すれば従来と同じ
```

### 7.2 CLI

```bash
# Job YAML の device_profile を上書きする
python -m app.cli generate job.yaml --profile dtg_synthetic_ct

# quick で選択する
python -m app.cli quick -p P000001 -m ct_generic --profile dtg_synthetic_ct \
  -s 1 -i 3 -o output/

# 読み込めるプロファイルの一覧（名前・モダリティ・製造者・型名・配置場所）
python -m app.cli profiles list
```

- `profiles list` は、壊れたプロファイルがあっても停止せずに一覧を出力し、壊れた
  ものは理由を添えて標準エラー出力に出す。終了コードは、1つでも壊れていれば 2
  （設定エラー）
- 終了コードは [04_cli.md](04_cli.md) のとおり。プロファイルのエラーは 2

### 7.3 古い名前のテンプレート

以前の、実在の装置の名前のテンプレートを `-m`・`modality_template` で指定
されたら、`TemplateNotFoundError` に「装置ごとの設定は装置プロファイルになった。
外部の配置場所に置き、`--profile` で選択する」という案内（`hint`）を添える。
古い名前は、名前そのものではなく SHA-256 のハッシュ値でコードに持つ
（`app/services/template_loader.py`。ADR-0016）。

---

## 8. モダリティエミュレーター（spec/12）との関係

- 撮影時にプロファイルを選択できる：設定 `modality.default_profile`
  （既定は無し）、撮影の画面の「装置」、CLI `exam --profile`
- プロファイルの `device.modality` と予約のモダリティが異なれば、テンプレートと
  同じく撮影の画面で停止する（[12a_web_screens_and_cli.md](12a_web_screens_and_cli.md)
  の 10.5）
- `services.mpps`・`services.storage_commitment` が `false` のプロファイルでは、
  設定で選択していても MPPS・保管確認を送信しない（装置が対応しない動作をしない。
  `app/modality/service.py` の `_profile_supports`・`_profile_allows`）
- `worklist` フィールド（予約から転記する項目の違いを、
  [12_modality_emulator.md](12_modality_emulator.md) の 6 章の表の上に重ねる）は
  **未実装**。現在の転記方法は 6 章の表のままで、プロファイルでは変えられない

---

## 9. エラー

`app/core/exceptions.py` にあり、[08_error_handling.md](08_error_handling.md) の
階層に載せてある。どれも `ConfigurationError` の下で、CLI の終了コードは 2。

```text
ConfigurationError
└── ProfileError                 # 配置場所のエラー（存在しないフォルダ）など
    ├── ProfileNotFoundError     # 名前が見つからない（検索した配置場所を添える）
    ├── ProfileParseError        # YAML のエラー・スキーマのエラー（ファイルとフィールドを添える）
    ├── DuplicateProfileError    # 同じ名前が2か所以上
    └── ProfileMismatchError     # テンプレート・Job と合わない（4.3）
```

エラーメッセージの例：

```text
Invalid device profile: /path/to/x.yaml
  (errors=device.manufacturer: Field required; private_tags.0.group: ...)
Device profile not found: abc (searched=/a, /b, /repo/profiles/examples)
```

---

## 10. テスト

| ファイル | 内容 |
|----------|------|
| `tests/core/test_device_profile.py` | モデルの検証（未知のフィールド・名前・UID・グループ・offset・VR・扱えない属性・重複）。Dataset に適用した結果（装置の値・属性・プライベートタグ） |
| `tests/services/test_profile_loader.py` | 外部のフォルダから読み込める・検索の順序・同じ名前のエラー・存在しないフォルダのエラー・壊れた YAML のエラー・リポジトリに例しか無いこと |
| `tests/services/test_study_generator_profile.py` | 架空のプロファイルで作成した画像に、製造者・型名・ソフトウェアバージョン・プライベートタグ・文字コード（IR 13＋IR 87 の漢字の氏名をデコードする）が入ること。合わないときに停止すること |
| `tests/cli/test_profile_commands.py` | `--profile`・`profiles list`・エラーの終了コード 2・古い名前の案内 |

---

## 11. 実装の状況

| 機能 | 状態 |
|------|------|
| モデル・読み込み・検証・重ね方（装置の値・Transfer Syntax・文字コード・属性・プライベートタグ）・CLI | 実装済み（10 章のテスト） |
| `exam --profile`・`modality.default_profile`・撮影の画面の「装置」 | 実装済み |
| `services.mpps`・`services.storage_commitment` を MPPS・保管確認に反映する（[12_modality_emulator.md](12_modality_emulator.md) の 8.3.3・8.4.1） | 実装済み。`services.modality_worklist` は反映しない |
| `uid`・`pixel`・`series` のフィールド。CT・MR 以外の SOP Class | 未実装。モデルにフィールドが無く、作成できる SOP Class は CT Image Storage と MR Image Storage だけ |
| `worklist` フィールド | 未実装 |

未実装のものは [roadmap.md](../roadmap.md) にもある。

---

## 12. 出典

2026-10-18 に参照したもの。

- DICOM PS3.2 2026d Annex N「DICOM Conformance Statement Template
  (Normative)」：N.1（Table N.1-1・N.1-2・N.1-5・N.1-15）、N.5、
  N.6、N.7（Table N.7-5）、N.9（Source と Presence の値、
  Table N.9-1〜N.9-21）
- DICOM PS3.2 2026d Annex A（古い形式。現在は Retired で、2022d を参照する）
- DICOM PS3.5 7.8（Private Data Elements）
- DICOM PS3.3 C.12.1.1.2（Specific Character Set）
