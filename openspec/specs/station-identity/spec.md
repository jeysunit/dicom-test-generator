# station-identity Specification

## Purpose

DTG がモダリティとして名乗る装置（AE タイトル・Station Name）を設定に複数持ち、
画面と CLI で切り替え、DICOM の通信と作る画像に反映することを定める。

## Requirements

### Requirement: 設定に複数の装置を書ける

DTG は、設定の装置の一覧に、装置ごとの表示名・AE タイトル・Station Name を
読み込まなければならない（SHALL）。AE タイトルは AE の VR（16 文字以内・空白だけは
不可・`\` を含まない。PS3.5 6.2）、Station Name は SH の VR（16 文字以内。PS3.5 6.2）
に合わなければならない。表示名と AE タイトルは一覧の中で重複してはならない
（SHALL NOT）。装置の一覧が無く、AE タイトルと Station Name だけの設定は、装置が
1つの一覧として読む。

#### Scenario: 2つの装置を読み込む

- **WHEN** 設定に `CT1号機`（`DTG_CT01`・Station Name `DTG_CT01`）と `MR1号機`（`DTG_MR01`・`DTG_MR01`）を書き、既定を `CT1号機` にして画面を起動する
- **THEN** 画面が起動し、情報バーに `CT1号機（DTG_CT01）` が表示される

#### Scenario: AE タイトルが重複している

- **WHEN** 設定の2つの装置に同じ AE タイトル `DTG_CT01` を書いて起動する
- **THEN** 起動せずに、設定の誤りとして項目の名前と原因を表示する

#### Scenario: 今の形の設定

- **WHEN** 設定に装置の一覧が無く、`ae_title: DTG_CT01` と `station_name: DTG_CT01` だけがある
- **THEN** 画面が起動し、装置が1つ（AE タイトル `DTG_CT01`）の状態で今と同じに動く

### Requirement: 画面で装置を切り替えられる

Web 画面は、情報バーで設定の装置から1つを選んで切り替えられなければならない
（SHALL）。選んだ装置は状態の保存先に記録し、画面を再起動しても使う。画面のプロセスの
中で撮影が走っているときと、送信中の件があるときは、切り替えを受け付けてはならない
（SHALL NOT）。撮影と送信は始めたときの装置の AE タイトルで最後まで行う。

#### Scenario: MR1号機に切り替える

- **WHEN** 利用者が情報バーで `MR1号機` を選ぶ
- **THEN** 情報バーの自分の AE タイトルが `DTG_MR01` になり、画面を再起動しても `MR1号機` が選ばれている

#### Scenario: 撮影の最中に切り替える

- **WHEN** 撮影が走っている間に、装置の切り替えの要求が届く
- **THEN** 切り替えは行われず、「撮影・送信の最中は装置を切り替えられません」と表示される

### Requirement: CLI はコマンドごとに装置を選べる

CLI は、画面と同じ記録の装置を使い、`--station <表示名>` を付けたコマンドだけ
その装置を使わなければならない（SHALL）。設定に無い表示名は、通信も作成もせずに
設定の誤りとして終了する。

#### Scenario: 1回だけ別の装置で撮る

- **WHEN** 画面で `CT1号機` を選んだ状態で、`python -m app.cli exam --station MR1号機 ...` を実行する
- **THEN** その撮影だけ `DTG_MR01` で通信と作成を行い、画面の選択は `CT1号機` のまま変わらない

#### Scenario: 設定に無い装置

- **WHEN** `--station XR9号機` を付けて実行する
- **THEN** 通信も作成もせずに、設定の誤りの終了コードで終了する

### Requirement: 選んだ装置の AE タイトルで名乗る

DTG は、ワークリストの C-FIND、C-STORE、C-ECHO、MPPS の N-CREATE・N-SET、
保管確認の N-ACTION の Association の Calling AE Title に、選んだ装置の AE タイトルを
使わなければならない（SHALL）。ワークリストの「この装置で絞る」は、
選んだ装置の AE タイトルを Scheduled Station AE Title (0040,0001) に入れる
（PS3.4 K.6.1.2.2）。

#### Scenario: MR1号機でワークリストを取得する

- **WHEN** `MR1号機` を選び、「この装置で絞る」でワークリストを取得する
- **THEN** C-FIND の Association の Calling AE Title と、Scheduled Procedure Step Sequence の (0040,0001) が `DTG_MR01` になる

#### Scenario: MR1号機で撮影して送る

- **WHEN** `MR1号機` を選び、MPPS を使う設定で「撮影して送信」を押す
- **THEN** MPPS と C-STORE の Association の Calling AE Title が `DTG_MR01` になり、MPPS の Performed Station AE Title (0040,0241) が `DTG_MR01`、Performed Station Name (0040,0242) が MR1号機の Station Name になる

#### Scenario: 予約の装置の印

- **WHEN** `MR1号機` を選び、「絞らない」で取得した一覧に (0040,0001) が `DTG_CT01` の予約がある
- **THEN** その行に「別の装置」の印が付き、`DTG_MR01` の予約には付かない

### Requirement: 作る画像に装置の値を入れる

DTG は、選んだ装置で作る画像の Station Name (0008,1010)（PS3.3 C.7.5.1）に装置の
Station Name を、File Meta の Source Application Entity Title (0002,0016)（PS3.10
7.1）に装置の AE タイトルを入れなければならない（SHALL）。装置の Station Name が
空なら、今の決まり（テンプレート・装置プロファイル・病院テンプレート）の値を使う。

#### Scenario: MR1号機で撮った画像

- **WHEN** Station Name が `DTG_MR01` の `MR1号機` を選んで撮影する
- **THEN** 作った画像の (0008,1010) が `DTG_MR01`、(0002,0016) が `DTG_MR01` になる

### Requirement: 送信と MPPS の再送は作ったときの装置で行う

送信キューの件と MPPS の行は、作ったときの装置の AE タイトルを記録し、再送と
保管確認の要求をその AE タイトルで行わなければならない（SHALL）。あとで装置を
切り替えても、記録した AE タイトルは変えない。画像を送るときは、画像を作った装置
（画像の Source Application Entity Title が設定の装置のどれか）の AE タイトルで名乗る。

#### Scenario: 撮った後に切り替えてから送る

- **WHEN** `CT1号機` で撮影し、`MR1号機` に切り替えた後に、その画像を送る
- **THEN** 送信の Association の Calling AE Title は `DTG_CT01` になる

#### Scenario: 切り替えた後に再送する

- **WHEN** `CT1号機` で送信して失敗した件を、`MR1号機` に切り替えた後に再送する
- **THEN** 再送の Association の Calling AE Title は `DTG_CT01` になる

### Requirement: 保管確認の結果はどの装置あてでも受ける

保管確認の結果を受ける待ち受けは、設定にある装置の AE タイトルあて（Called AE
Title）の Association を受け、それ以外は拒否しなければならない（SHALL）。結果は、
要求を送った装置の AE タイトルあてに届いたものだけを、その要求の結果にする
（PS3.4 J.3.3）。

#### Scenario: 切り替えた後に結果が届く

- **WHEN** `CT1号機` で保管確認を求めた後に `MR1号機` に切り替え、相手が `DTG_CT01` あてに N-EVENT-REPORT を送る
- **THEN** 結果を受け、その件が「確認済」になる

#### Scenario: 設定に無い AE タイトルあて

- **WHEN** 相手が `DTG_XR99` あてに Association を求める
- **THEN** 待ち受けは Association を拒否する（理由 7「called-AE-title-not-recognized」。PS3.8 9.3.4）

### Requirement: 登録されていない AE タイトルを理由に拒否されたら知らせる

DTG は、相手が A-ASSOCIATE-RJ の理由 3「calling-AE-title-not-recognized」
（PS3.8 9.3.4）で Association を拒否したとき、使った AE タイトルと、相手の側に
登録が要ることを知らせなければならない（SHALL）。

#### Scenario: PACS に MR1号機が登録されていない

- **WHEN** `MR1号機` で送信し、PACS が理由 3 で Association を拒否する
- **THEN** 送信失敗になり、理由に「相手が AE タイトル DTG_MR01 を受け付けませんでした。相手の側に、この装置の AE タイトルを登録してください」と表示される
