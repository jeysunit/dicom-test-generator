# Spec Delta

## MODIFIED Requirements

### Requirement: モダリティごとの形のルーチンを持つ

DTG は、DTG が扱うモダリティ（CT・MR・CR・DX・US）ごとに、そのモダリティの形の
ルーチンを持たなければならない（SHALL）。CT はシリーズの種類と再構成、MR は
シーケンス（ADC は DWI と別のシリーズ）、CR は方向ごとに1シリーズ1枚、DX は
1シリーズに全部の方向、US は静止画と動画の数を持つ。どのルーチンも、すべての
シリーズに標準の画像数を持ち、各モダリティに標準のルーチンが1つある。画像を
作れないモダリティ（今は US）の予約は、テンプレートのモダリティと違うことを
知らせて撮影しない。CR・DX の予約は、`cr_generic`・`dx_generic` のテンプレートで
ルーチンの並びのとおりに撮る。

#### Scenario: MR のルーチン

- **WHEN** `templates/routine/` の MR のルーチンを読み込む
- **THEN** 頭部・腰椎・膝・肩の4つがあり、初期設定は頭部で、頭部の並びはローカライザー 15 枚から始まり、ADC は DWI と別のシリーズになっている

#### Scenario: CR と DX の胸部

- **WHEN** CR と DX の「胸部」のルーチンを読み込む
- **THEN** どちらも PA と側面の各1枚で、CR は2つのシリーズ、DX は1つのシリーズになっている

#### Scenario: CR の予約

- **WHEN** モダリティ CR の予約で撮影の画面を開く
- **THEN** CR の標準のルーチン「胸部」が当たり、テンプレートは `cr_generic` になり、撮影できる

#### Scenario: US の予約

- **WHEN** テンプレートに US が無いときに、モダリティ US の予約で撮影の画面を開く
- **THEN** US の標準のルーチン「腹部」が当たるが、「予約は US、テンプレートは CT です」と知らせて撮影は押せない

## ADDED Requirements

### Requirement: ルーチンに図形の部位と撮像の区別を書ける

DTG は、ルーチンの YAML に、図形の部位 `phantom`（`head`・`chest`・`trunk`・
`abdomen`・`spine`・`limb`）を書けなければならない（SHALL）。CR・DX のルーチンは
部位 `body_part`（Body Part Examined の語。`CHEST`・`ABDOMEN`・`LSPINE`・`CSPINE`・
`KNEE`・`HAND`）を必ず持ち、対になる部位（`KNEE`・`HAND`）は左右 `laterality` を
必ず持つ。`laterality` は CR では `R`・`L`、DX では `R`・`L`・`B` で、対にならない
部位には書けない。CR の対になる部位は Laterality (0020,0060)、DX は Image
Laterality (0020,0062) に入れ、DX の対にならない部位の Image Laterality は `U` に
する（PS3.3 C.7.3.1・C.8.11.2）。MR のシリーズには強調 `weighting`（`T1`・`T2`・`PD`・
`FLAIR`・`T2STAR`・`DWI`・`ADC`・`MRA`）、CT の造影のシリーズには相 `phase`
（`arterial`・`portal`・`delayed`）を書ける。`phantom`・`weighting`・`phase` は
省ける。`weighting` を省いた MR のシリーズはシーケンスから決め、`phase` を省いた
造影のシリーズは `portal` にする。付けるルーチンには、design.md の「検査ごとの
シリーズの構成」の値を書く。

#### Scenario: 付けるルーチンの値

- **WHEN** `templates/routine/` を読み込む
- **THEN** `ct_head_plain` と `mr_head` の `phantom` は `head`、`dx_knee` の `body_part` は `KNEE` で `laterality` は `R`、`mr_head` の FLAIR の `weighting` は `FLAIR` になっている

#### Scenario: 対になる部位の左右が無い

- **WHEN** `body_part: KNEE` で `laterality` の無い CR のルーチンを読み込む
- **THEN** ルーチンは読み込まれず、設定の誤りとして知らせる

#### Scenario: CR の両側

- **WHEN** CR のルーチンに `laterality: B` を書く
- **THEN** ルーチンは読み込まれず、設定の誤りとして知らせる（CR の Laterality は `R`・`L` だけ）

#### Scenario: 対にならない部位の左右

- **WHEN** `body_part: CHEST` の DX のルーチンに `laterality: R` を書く
- **THEN** ルーチンは読み込まれず、設定の誤りとして知らせる

#### Scenario: 造影でないシリーズの相

- **WHEN** `contrast` の無い CT のシリーズに `phase` を書く
- **THEN** ルーチンは読み込まれず、設定の誤りとして知らせる
