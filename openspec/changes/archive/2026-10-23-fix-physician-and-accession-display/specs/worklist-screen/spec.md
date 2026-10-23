# Spec Delta

## Purpose

Web 画面のワークリストで、予約を取得し、選び、選んだ予約を取得し直す操作と、
失敗したときに利用者へ出す知らせを定める。

## ADDED Requirements

### Requirement: 予約の詳細に依頼医と紹介医を分けて示す

予約の詳細のパネルは、Requesting Physician (0032,1032)（PS3.3 C.4.12）を「依頼医」、
Referring Physician's Name (0008,0090)（PS3.3 C.7.2.1）を「紹介医」として、別の行に
表示しなければならない（SHALL）。値が空なら「—」を表示する。

#### Scenario: 両方の値がある予約

- **WHEN** (0032,1032) が `Sato^Ichiro`、(0008,0090) が `Suzuki^Hanako` の予約の行を選ぶ
- **THEN** 詳細のパネルに「依頼医 Sato Ichiro」と「紹介医 Suzuki Hanako」が表示される

#### Scenario: 依頼医が空の予約

- **WHEN** (0032,1032) が空か応答に無い予約の行を選ぶ
- **THEN** 「依頼医」の行に「—」が表示される
