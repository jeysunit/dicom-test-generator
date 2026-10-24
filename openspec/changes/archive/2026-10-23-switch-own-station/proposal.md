# Proposal

## Why

DTG はモダリティの代わりをするが、自分の AE タイトルと Station Name は設定の
1つ（`modality.ae_title`・`modality.station_name`）だけで、変えるには設定ファイルを
書き換えて画面を再起動する必要がある。RIS・PACS のテストでは、CT1号機
（`DTG_CT01`）と MR1号機（`DTG_MR01`）のように複数の装置からの検査を続けて作りたい。
装置の一覧を設定に書き、画面で切り替えられるようにする。

PACS・RIS は、登録していない Calling AE Title からの Association を拒否できる
（A-ASSOCIATE-RJ の理由 3「calling-AE-title-not-recognized」。PS3.8 9.3.4）。
切り替えた装置の AE タイトルは、相手の側に登録されていないと受け付けられないことを、
画面と知らせで分かるようにする。

## What Changes

- 設定に装置の一覧 `modality.stations:`（表示名・AE タイトル・Station Name）と
  既定の装置を書けるようにする。今の `ae_title`・`station_name` だけの設定は、
  装置が1つの設定として読む（設定を書き換えずに動く）
- 画面のヘッダーの下の情報バーで、装置を選んで切り替える。選んだ装置は状態の
  保存先に記録し、画面を再起動しても残す。CLI は同じ記録を使い、`--station <表示名>`
  でそのコマンドだけ別の装置にできる
- 選んだ装置の AE タイトルを、ワークリストの C-FIND・C-STORE・C-ECHO・MPPS・
  保管確認の Calling AE Title に使う。ワークリストの「この装置で絞る」も
  選んだ装置の AE タイトルで絞る
- 作る画像の Station Name (0008,1010) と File Meta の Source Application Entity
  Title (0002,0016) を、選んだ装置の値にする。MPPS の Performed Station AE Title
  (0040,0241)・Performed Station Name (0040,0242) も同じ
- 送信キューの件と MPPS の行は、作ったときの装置の AE タイトルを記録し、再送でも
  その AE タイトルで送る（あとで装置を切り替えても変わらない）
- 保管確認の結果（N-EVENT-REPORT）は、設定にあるどの装置の AE タイトルあてでも
  受け、要求を送った装置の AE タイトルと合うものだけを結果にする
- 相手が Calling AE Title を理由に Association を拒否したら、「相手が AE タイトル
  DTG_MR01 を受け付けませんでした。相手の側に、この装置の AE タイトルを登録して
  ください」と知らせる

## Capabilities

### New Capabilities

- `station-identity`: DTG が名乗る装置（AE タイトル・Station Name）の一覧と切り替え、
  通信と画像への反映

### Modified Capabilities

（なし）

## Impact

- 設定：`app/modality/config.py`（`stations`・`default_station`、今の形の読み込み）、
  `config/app_config.yaml` の例
- サービス：`app/modality/service.py`（選んだ装置の値を各 SCU と作成に渡す）、
  `app/modality/queue.py`・`mpps_queue.py`（行に AE タイトルを記録する列。既存の DB は
  列を足して今の AE タイトルで埋める）、`commitment_scu.py`（待ち受けの Called AE）、
  `association.py`（拒否の理由）
- 画像の作成：`app/services/study_generator.py`（Station Name の優先順）
- 画面：情報バー（`_band.html`）、設定の画面、`app/web/routes/`
- CLI：`--station` のオプション、`app/cli/modality_commands.py`
- spec：12 の 4・6.2・8・12 章、12a の 10.3・10.4・10.7・11 章、13 の Station Name
- ADR：装置の切り替えと、Station Name の優先順の決定
- 利用者：PACS・RIS に、使う装置の AE タイトルをすべて登録する必要がある
