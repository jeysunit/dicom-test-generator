# Spec Delta

## MODIFIED Requirements

### Requirement: 予約の詳細に依頼医と紹介医を分けて示す

予約の詳細のパネルは、患者の氏名を「氏名」、Requesting Physician (0032,1032)（PS3.3 C.4.12）を
「依頼医」、Referring Physician's Name (0008,0090)（PS3.3 C.7.2.1）を「紹介医」として、
別の行に表示しなければならない（SHALL）。3 つとも、成分の区切り `^` と成分グループの
区切り `=` を出さず、一覧の氏名と同じ順（漢字・かな・英字）に ` / ` で区切る。値が
空なら「—」を表示する。

#### Scenario: 両方の値がある予約

- **WHEN** (0032,1032) が `Sato^Ichiro`、(0008,0090) が `Suzuki^Hanako` の予約の行を選ぶ
- **THEN** 詳細のパネルに「依頼医 Sato Ichiro」と「紹介医 Suzuki Hanako」が表示される

#### Scenario: 依頼医が空の予約

- **WHEN** (0032,1032) が空か応答に無い予約の行を選ぶ
- **THEN** 「依頼医」の行に「—」が表示される

#### Scenario: 漢字・かな・英字がそろった氏名

- **WHEN** 氏名が `YAMADA^TARO=山田^太郎=やまだ^たろう` の予約の行を選ぶ
- **THEN** 詳細のパネルの「氏名」は「山田 太郎 / やまだ たろう / YAMADA TARO」で、`^` と `=` は出ない
