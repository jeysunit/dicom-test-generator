# exam-workflow Specification

## Purpose

予約（Scheduled Procedure Step）で撮影したとき、その予約を撮影済みにする決まりと、
撮り直しの2つの形（同じ予約での追加撮影＝IHE の Append Case と、RIS の新しい予約での
撮り直し）の選び方、画像・MPPS の値を定める。

## Requirements

### Requirement: 予約での撮影は1回で撮影済みになる

DTG は、予約で撮影を終えたら、その予約を撮影済みとして記録しなければならない
（SHALL）。撮影済みの予約では、撮影の画面の「撮影」「撮影して送信」を押せなく
し、同じ予約での通常の撮影の要求を断らなければならない（SHALL）。撮影済みかは
予約ごとに記録し、ワークリストを取得し直しても残す。

#### Scenario: 撮影して送った後

- **WHEN** 利用者が受付番号 `A0001` の予約で「撮影して送信」を押し、撮影が終わる
- **THEN** 撮影の画面の「撮影」「撮影して送信」は押せなくなる

#### Scenario: 撮影済みの予約で撮影の要求が届く

- **WHEN** 撮影済みの予約で、通常の撮影の要求がサーバーに届く（画面を開き直した、CLI で同じ予約を指定した、など）
- **THEN** 画像は作られず、撮影済みであることと撮り直しの方法（設定の撮り直しの形による）を知らせ、CLI は入力の誤りの終了コードで終了する

#### Scenario: 一覧の印

- **WHEN** 撮影済みの予約を含むワークリストを取得する
- **THEN** その行に「撮影済み」の印が付く

### Requirement: 撮り直しの形を設定で選べる

DTG は、撮影済みの予約の撮り直しの形を、設定で `append`（IHE の Append Case。
IHE RAD TF-2 4.6.4.1.2.3.3）と `new_order`（撮り直しを別の検査として扱う施設の
ローカルルール）から選べなければならない（SHALL）。既定は `append` とする。
設定に無い値は、起動せずに設定の誤りとして知らせる。

#### Scenario: append の撮影済みの予約

- **WHEN** 撮り直しの形が `append` で、撮影済みの予約を撮影の画面で開く
- **THEN** 「撮影」「撮影して送信」は押せず、「追加撮影」が表示される

#### Scenario: 設定を書かない

- **WHEN** 設定に撮り直しの形を書かずに起動する
- **THEN** 撮り直しの形は `append` になる

#### Scenario: 設定に無い値

- **WHEN** 撮り直しの形に `copy` と書いて起動する
- **THEN** 起動せずに、項目の名前と原因を設定の誤りとして表示する

### Requirement: new_order では RIS の新しい予約で撮り直す

撮り直しの形が `new_order` のとき、DTG は撮影済みの予約に「追加撮影」を出しては
ならず（SHALL NOT）、「撮り直しの予約が要ります（RIS で新しい予約を作って
ください）」と表示しなければならない（SHALL）。DTG は受付番号も Study Instance UID
も作らず、RIS が作った新しい予約をワークリストで取得し直して、通常の撮影を行う。

#### Scenario: new_order の撮影済みの予約

- **WHEN** 撮り直しの形が `new_order` で、撮影済みの予約を撮影の画面で開く
- **THEN** 「撮影」「撮影して送信」は押せず、「追加撮影」は表示されず、「撮り直しの予約が要ります（RIS で新しい予約を作ってください）」と表示される

#### Scenario: new_order で追加撮影の要求が届く

- **WHEN** 撮り直しの形が `new_order` で、追加撮影の要求（CLI の `--append` など）が届く
- **THEN** 画像は作られず、撮り直しの予約が要ることを知らせ、CLI は入力の誤りの終了コードで終了する

#### Scenario: RIS が作った撮り直しの予約で撮る

- **WHEN** 撮り直しの形が `new_order` で、RIS が別の受付番号・Study Instance UID の撮り直しの予約を作り、利用者がワークリストを取得し直してそれを選び、撮影する
- **THEN** 新しい予約の受付番号と Study Instance UID で画像と MPPS が作られ、前の予約の撮影済みの記録は変わらない

### Requirement: 撮影が止まった予約は撮影済みにしない

DTG は、撮影が途中で止まった（MPPS を使うときは DISCONTINUED を送った。PS3.4
F.7.2.2.2）予約を撮影済みにしてはならない（SHALL NOT）。その予約では、もう一度
通常の撮影ができる。

#### Scenario: 撮影が止まった後に撮り直す

- **WHEN** 予約で撮影が途中で止まり、MPPS に DISCONTINUED を送った後、同じ予約で「撮影」を押す
- **THEN** 撮影でき、新しい MPPS の SOP Instance（N-CREATE）で記録される

### Requirement: 撮影済みの予約で終わった MPPS は更新しない

DTG は、COMPLETED か DISCONTINUED を送った MPPS の SOP Instance に、N-SET を
送ってはならず、その MPPS の一部として画像を作ってはならない（SHALL NOT。
PS3.4 F.7.2.2.2）。続けて画像を作るときは、新しい MPPS の SOP Instance を作る。

#### Scenario: 追加撮影の MPPS

- **WHEN** MPPS を使う設定で、撮影済みの予約で「追加撮影」を押す
- **THEN** 1回目と異なる MPPS の SOP Instance UID で N-CREATE（IN PROGRESS）と N-SET（COMPLETED）が送られ、1回目の MPPS には何も送られない

### Requirement: 追加撮影は同じ Study に新しいシリーズを足す

撮り直しの形が `append` のとき、追加撮影は IHE の Append Case（IHE RAD TF-2 4.6.4.1.2.3.3、RAD TF-2x Table
A.1-3）に従わなければならない（SHALL）。Study Instance UID・受付番号・Request
Attributes Sequence の値は元の予約と同じにし、シリーズは新しい Series Instance
UID で作る（RAD TF-2 4.8.4.1.1.1）。MPPS の Scheduled Step Attributes Sequence は
元の予約を指す。

#### Scenario: 予約に Study Instance UID がある

- **WHEN** Study Instance UID が `1.2.3.4` の予約で撮影し、続けて「追加撮影」を押す
- **THEN** 追加撮影の画像の Study Instance UID は `1.2.3.4`、受付番号と Request Attributes Sequence の Scheduled Procedure Step ID は元の予約と同じで、Series Instance UID は1回目のどのシリーズとも異なる

#### Scenario: 予約に Study Instance UID が無い

- **WHEN** Study Instance UID の無い予約で撮影し（DTG が UID を作る）、続けて「追加撮影」を押す
- **THEN** 追加撮影の画像の Study Instance UID は、1回目に DTG が作った UID と同じになる

### Requirement: 追加撮影の Study の日時と説明は最初の撮影の値にする

追加撮影の画像の Study Date (0008,0020)・Study Time (0008,0030)・Study
Description (0008,1030) は、その予約の最初の撮影の値にしなければならない（SHALL。
IHE RAD TF-2x Appendix A の IHE-A.3.3）。Series Number は、その予約で前に作った
シリーズの続きの番号にする。

#### Scenario: 翌日に追加撮影する

- **WHEN** 2026-10-23 10:00 に予約で撮影（シリーズ 2 つ）し、2026-10-24 09:00 に同じ予約で「追加撮影」（シリーズ 1 つ）を押す
- **THEN** 追加撮影の画像の Study Date は `20261023`、Study Time は 1回目と同じ値、Study Description は 1回目と同じで、Series Number は `3` になる

### Requirement: 予約の Study Instance UID と受付番号を作り替えない

DTG は、どの撮り直しの形でも、Study Instance UID のある予約で新しい Study
Instance UID を作ってはならず（SHALL NOT。IHE RAD TF-2 4.8.4.1.1.1）、予約の
受付番号と異なる受付番号を作ってはならない（SHALL NOT。受付番号は RIS が発番する。
IHE RAD TF-2x Table A.1-1・A.1-3）。

#### Scenario: 撮影済みの予約の撮り直し

- **WHEN** Study Instance UID が `1.2.3.4`・受付番号が `A0001` の撮影済みの予約を、どちらかの撮り直しの形で撮り直そうとする
- **THEN** `1.2.3.4` 以外の Study Instance UID と `A0001` 以外の受付番号を持つ画像は、その予約からは作られない
