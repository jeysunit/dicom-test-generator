# DICOM Test Data Generator

- 作成日：2026-02-22
- 最終更新日：2026-10-22

DICOM Test Data Generator（DTG）は、架空の患者の DICOM データを生成して送信する、
テスト用のツールです。CT などのモダリティとして動作し、ワークリスト（検査の予約の
一覧）を取得して、予約の内容で生成した画像を PACS へ送信することもできます。
PACS・RIS・ビューア・画像の取り込みシステムの検証、開発、デバッグに使います。

画像の中身はテスト用に合成したもので、実際の医療画像ではありません。個人情報を
含まないので、テストに安全に使えます。

- **医療機器ではありません。** 診断・医療行為・臨床評価・AI の学習用の医療画像の
  生成には使えません
- 本番の PACS には送信せず、テスト用の PACS・RIS にだけ接続してください

## できること

### DICOM データの生成

- Study・Series・Instance の階層、UID（UUID ベースの 2.25 の形式）、マルチスライスの
  空間座標、Transfer Syntax の選択
- 日本語の患者名（Specific Character Set。PN の英字・漢字・かなの表記）
- ピクセルの生成：簡易モード（UID の文字列を描画する）と CT モード（16 ビットの
  HU 値）。どちらも実際の画像ではありません
- 異常のデータの生成：必須タグの欠落、VR の違反、文字数の超過、不正な UID、
  Pixel Data の欠落。レベル（none・mild・moderate・severe）は Job YAML の
  `abnormal.level` か `--abnormal-level` で選びます。指定しなければ、規格どおりの
  データを生成します
- モダリティテンプレート、病院テンプレート、YAML の Job による設定
- 装置プロファイル：装置の DICOM コンフォーマンスステートメントの内容を転記し、
  その装置の DICOM の出力を再現します。実在の装置のプロファイルはリポジトリの
  外に置きます（[docs/spec/13](docs/spec/13_device_profiles.md)）

### モダリティとしての動作

Web 画面と CLI で、ワークリストの取得、予約の選択、撮影（テスト用の画像の生成）、
PACS への送信、結果の確認までを行います
（[docs/spec/12](docs/spec/12_modality_emulator.md)）。

- ワークリストの取得（MWL）
- 画像の送信（C-STORE）、疎通確認（C-ECHO）、送信に失敗した画像のキューと再送
- 予約の無い緊急の患者の入力
- 保管確認（Storage Commitment）：送信した画像を相手が保管したかを問い合わせる。
  有効にしたときだけ
- MPPS：撮影の開始と終了を相手に通知する。有効にしたときだけ

画像を受信して保存する機能（Storage SCP）はありません。受信側には、テスト用の
PACS（Orthanc など）を用意してください。

PySide6 のデスクトップ画面（`python -m app.gui`）は基本の生成機能だけを持ち、機能は
追加していません。Web 画面を使ってください。

## 動作環境

- Python 3.10 以上
- Windows・Linux・macOS

## インストール

```bash
git clone https://github.com/jeysunit/dicom-test-generator.git
cd dicom-test-generator

python -m venv .venv

# Linux・macOS
source .venv/bin/activate

# Windows（PowerShell）
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Docker で動かす

`Dockerfile` で、CLI と Web 画面のイメージをビルドできます（デスクトップ画面は
含みません）。コンテナは root 以外のユーザー（uid 10001）で動作します。

```bash
docker build -t dicom-test-generator .
```

設定ファイルはコンテナの外に置き、`/app/config/app_config.yaml` にマウントします。
Web 画面はコンテナの中で `0.0.0.0` にバインドするので、設定の `web.bind_address` を
`"0.0.0.0"` にし、HTTP Basic 認証のパスワードのファイルを渡します（下の
「ネットワークに公開するとき」）。設定ファイルとパスワードのファイルは、リポジトリの
外（例：`~/dtg/`）に置きます。次の例は、ポートをホストの 127.0.0.1 にだけ公開
します。

```bash
docker run -d --name dtg -p 127.0.0.1:8080:8080 \
  -v "$HOME/dtg/app_config.yaml:/app/config/app_config.yaml:ro" \
  -v "$HOME/dtg/password.txt:/run/secrets/dtg_web_password:ro" \
  -e DTG_WEB_PASSWORD_FILE=/run/secrets/dtg_web_password \
  -v dtg-state:/app/modality_state -v dtg-output:/app/output \
  dicom-test-generator

# CLI は同じコンテナの中で実行する
docker exec dtg python -m app.cli echo --to PACS_TEST
```

- 送信先とワークリストの取得先は、設定ファイルの `modality:` の節に書きます。
  コンテナから到達できるホスト名か IP アドレスにします
- 予約の結果と送信キューは `/app/modality_state`、生成した画像は `/app/output` に
  書き出します。残すときはボリュームをマウントします
- パスワードのファイルは、コンテナの中のユーザー（uid 10001）が読めるようにします
  （例：`chmod 0644`）
- ボリュームの代わりにホストのディレクトリをバインドマウントするときは、その
  ディレクトリに uid 10001 が書き込めるようにします
- この手順では、保管確認の結果は受け取れません。受け取るには、設定の
  `modality.listen.bind_address` を `"0.0.0.0"` にし、待ち受けのポート（既定
  11113）も公開します
- イメージにヘルスチェックは入れていません

## DICOM ファイルの生成（CLI）

```bash
# Job YAML から生成する
python -m app.cli generate examples/job_minimal.yaml

# 出力先を指定して生成する
python -m app.cli generate examples/job_full.yaml -o output/ --verbose

# 設定を検証するだけ（生成しない）
python -m app.cli validate examples/job_minimal.yaml

# 引数だけで簡易に生成する
python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o output/

# 装置プロファイルを重ねて生成する
python -m app.cli quick -p P000001 -m ct_generic --profile dtg_synthetic_ct -s 1 -i 3 -o output/

# 異常のデータを生成する（none・mild・moderate・severe）
python -m app.cli quick -p P000001 -m ct_generic -s 1 -i 5 -o output/ --abnormal-level mild

# 読み込める装置プロファイルの一覧
python -m app.cli profiles list

# バージョン
python -m app.cli version
```

生成の条件は Job YAML に書きます。`examples/` に、最小の例とすべての項目を書いた
例があります。引数の詳細は各サブコマンドの `--help` を見てください
（[docs/spec/04](docs/spec/04_cli.md)）。

### Job YAML の例

```yaml
job_name: "テスト生成"
output_dir: "output/test"

patient:
  patient_id: "TEST001"
  patient_name:
    alphabetic: "YAMADA^TARO"
  birth_date: "20000101"
  sex: "M"

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "120000"
  num_series: 1

series_list:
  - series_number: 1
    num_images: 10

modality_template: "ct_generic"
pixel_spec:
  mode: "simple_text"

transfer_syntax:
  uid: "1.2.840.10008.1.2"
  name: "Implicit VR Little Endian"
  is_implicit_vr: true
  is_little_endian: true

character_set:
  specific_character_set: ""       # 日本語名の場合: "ISO 2022 IR 6\\ISO 2022 IR 87"
  use_ideographic: false            # 日本語名の場合: true
  use_phonetic: false               # 日本語名の場合: true
```

項目の意味は [docs/spec/07](docs/spec/07_job_schema.md) にあります。

## モダリティとして使う

### Web 画面

ワークリスト・撮影・PACS・設定の4つの画面で「取得 → 選択 → 撮影 → 送信 → 確認」を
行います（[docs/spec/12a](docs/spec/12a_web_screens_and_cli.md) の 10 章）。

```bash
# 設定は config/app_config.yaml の modality: と web: の節
python -m app.web
python -m app.web --config config/app_config.yaml
```

ブラウザで <http://127.0.0.1:8080/> を開きます。既定ではループバック（127.0.0.1）
だけで待ち受け、認証はありません。Node も Tailwind CSS の実行ファイルも不要です
（生成済みの CSS と htmx を `app/web/static/` に置いてあります）。

### ネットワークに公開するとき

`web.bind_address` をループバック以外（`0.0.0.0` など）にするときは、HTTP Basic
認証が必須です。パスワードを1行だけ書いたファイルを作成し、環境変数で指定します。
ファイルが無いか空のときは起動しません（終了コード 2）。ユーザー名は `dtg` です。

```bash
DTG_WEB_PASSWORD_FILE=/path/to/password.txt python -m app.web
```

- パスワードは設定ファイルに書きません
- この画面は HTTPS に対応していません。ネットワークに公開するときは、前段の
  リバースプロキシで TLS を終端してください（`Host` ヘッダーをそのまま渡す設定に
  します）
- 書き込みのリクエストは、同一オリジンで CSRF トークンが正しいときだけ受け付けます

### CLI

```bash
python -m app.cli echo --to PACS_TEST
python -m app.cli worklist query --json
python -m app.cli exam --from-worklist <キー> -s 2 -i 1,20 --send
python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO"
python -m app.cli queue list --status failed
python -m app.cli queue retry --all
```

コマンドの一覧と終了コードは [docs/spec/12a](docs/spec/12a_web_screens_and_cli.md)
の 11 章にあります。

### 保管確認と MPPS

どちらも既定では無効です。`config/app_config.yaml` の `modality:` の節で有効に
します（[docs/spec/12](docs/spec/12_modality_emulator.md) の 8.3・8.4・12 章）。

#### 保管確認（Storage Commitment）

```yaml
modality:
  listen:                       # 結果（N-EVENT-REPORT）を受ける待ち受け
    bind_address: "127.0.0.1"
    port: 11113
  destinations:
    - name: "PACS_TEST"
      ae_title: "PACS_TEST"
      host: "127.0.0.1"
      port: 4242
      storage_commitment: true
      commitment_timeout_seconds: 600   # 結果を待つ秒数
      commitment_wait_seconds: 0        # 同じ Association で待つ秒数（0 は待たない）
```

- Web 画面（`python -m app.web`）は待ち受けを起動し、送信に成功した画像の
  保管確認をすぐに要求します。PACS の画面の送信キューの「保管の確認」の列に、
  確認待ち・確認済・確認の失敗・確認の時間切れのどれかが表示されます
- CLI では自動で要求しません。送信の後に `commit` で要求し、結果を待ちます。
  確認済なら終了コード 0、それ以外は 5 です。Web 画面が同じポートで待ち受けて
  いるときは待ち受けを起動できないので、終了コード 2 で停止します

```bash
python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO" --send
python -m app.cli queue list               # ジョブの ID と COMMIT の列
python -m app.cli commit --job 1 --wait 60
```

- 結果は、相手が別の Association で返すことを前提にしています。同じ Association
  でしか返さない相手のときだけ、`commitment_wait_seconds` に秒数を設定します

#### Orthanc で保管確認をテストする

この手順は、まだ Orthanc を相手に実行して確認していません
（[docs/roadmap.md](docs/roadmap.md)）。

Orthanc（1.6.0 以降）は保管確認を受け付け、結果を別の Association で返します。
結果の返送先として、DTG を Orthanc の設定の `DicomModalities` に登録します。

1. Orthanc の設定に、DTG の AE タイトル・IP アドレス・待ち受けのポートを追加します
   （例：`"DicomModalities": { "dtg": [ "DTG_CT01", "127.0.0.1", 11113 ] }`）。
   Orthanc をコンテナで動かすときは、コンテナから到達できる IP アドレスを書き、DTG の
   `listen.bind_address` もそのアドレスで待ち受けるようにします（既定の 127.0.0.1
   にはコンテナから到達できません）
2. DTG の送信先を Orthanc の AE タイトル・IP アドレス・DICOM のポートにし、
   `storage_commitment: true` にします
3. `python -m app.web` を起動し、撮影の画面で [撮影して送る] を押します
4. PACS の画面の送信キューで、そのジョブの「保管の確認」が「確認済」になることを
   確認します。CLI では、Web 画面を停止してから
   `python -m app.cli commit --job <ID>` を実行し、`confirmed` と終了コード 0 が
   返ることを確認します

#### MPPS

```yaml
modality:
  worklist:
    use_mpps: true              # MPPS を送信する
  mpps:                         # 省略したときはワークリストの取得先へ送信する
    ae_title: "MPPS_TEST"
    host: "127.0.0.1"
    port: 4243
    timeout_seconds: 30
```

- 撮影の開始で N-CREATE（IN PROGRESS）、画像を生成し終えたら N-SET（COMPLETED）を
  送信します。生成の途中で停止したときは N-SET（DISCONTINUED）を送信します
- MPPS を送信できなくても、撮影と画像の送信は止めません。撮影の画面と CLI
  （`[WARN] MPPS ...`）に表示し、通知をキューに残します。`retry.max_attempts` の
  回数だけすぐに再送し、残りは `mpps retry` で送信します
- `exam --mpps`・`--no-mpps` で、その撮影だけ設定を上書きできます。装置
  プロファイルが `services.mpps: false` なら送信しません
- Orthanc は MPPS を受け付けません。MPPS を受け付けるテスト用の相手（RIS など）を
  使ってください

```bash
python -m app.cli mpps list
python -m app.cli mpps retry
```

## 開発者向けの文書

文書は [docs/](docs/README.md) にあります。

- [docs/project_charter.md](docs/project_charter.md)：目的、範囲、規格の前提
- [docs/architecture.md](docs/architecture.md)：構成と層
- [docs/spec/](docs/spec/)：現在の動作
- [docs/decisions/](docs/decisions/README.md)：設計の判断と理由（ADR）
- [docs/development.md](docs/development.md)：開発環境、テスト、変更の手順

Issue と Pull Request を受け付けています。

## ライセンス

MIT License

本ソフトウェアの使用によって生じたいかなる損害についても、作者は責任を負いません。

## 関連する資料

- DICOM Standard：<https://www.dicomstandard.org/>
- pydicom：<https://pydicom.github.io/>
- pynetdicom：<https://pydicom.github.io/pynetdicom/>
