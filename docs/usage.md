# 使い方

DTG を使う操作を、順番に説明します。コマンドのオプションと設定の項目の一覧は
spec にあります（CLI は [spec/04](spec/04_cli.md) と
[spec/12a](spec/12a_web_screens_and_cli.md) の 11 章、設定は
[spec/12](spec/12_modality_emulator.md) の 12 章、Job YAML は
[spec/07](spec/07_job_schema.md)）。

本番の PACS には送信せず、テスト用の PACS・RIS にだけ接続してください。

## 1. インストールする

Python 3.10 以上が必要です。Windows・Linux・macOS で動作します。

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

### Docker で動かすとき

`Dockerfile` で、CLI と Web 画面のイメージをビルドできます（デスクトップ画面は
含みません）。コンテナは root 以外のユーザー（uid 10001）で動作します。

```bash
docker build -t dicom-test-generator .
```

設定ファイルとパスワードのファイルはリポジトリの外（例：`~/dtg/`）に置き、
コンテナにマウントします。コンテナの中では Web 画面が `0.0.0.0` にバインドする
ので、設定の `web.bind_address` を `"0.0.0.0"` にし、パスワードのファイルを渡します
（4 章の「ネットワークに公開するとき」）。次の例は、ポートをホストの 127.0.0.1 に
だけ公開します。

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

- 送信先とワークリストの取得先には、コンテナから到達できるホスト名か IP アドレスを
  設定します
- 予約の結果と送信キューは `/app/modality_state`、生成した画像は `/app/output` に
  書き出します。残すときはボリュームをマウントします
- パスワードのファイルと、バインドマウントするホストのディレクトリは、uid 10001 が
  読み書きできるようにします（例：`chmod 0644`）
- 保管確認の結果を受け取るには、設定の `modality.listen.bind_address` を
  `"0.0.0.0"` にし、待ち受けのポート（既定 11113）も公開します
- イメージにヘルスチェックは入れていません

## 2. DICOM ファイルを生成する

生成の条件は Job YAML に書きます。`examples/` に、最小の例（`job_minimal.yaml`）と
すべての項目を書いた例（`job_full.yaml`）があります。

```bash
# Job YAML の設定を検証する（生成しない）
python -m app.cli validate examples/job_minimal.yaml

# Job YAML から生成する
python -m app.cli generate examples/job_minimal.yaml
python -m app.cli generate examples/job_full.yaml -o output/ --verbose
```

Job YAML を書かずに、引数だけで生成することもできます。

```bash
python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o output/
```

用途に応じて、次のオプションを付けます。

- 異常のデータを生成する：`--abnormal-level mild`（`none`・`mild`・`moderate`・
  `severe`）。指定しなければ規格どおりのデータを生成します
- 装置プロファイルを重ねる：`--profile dtg_synthetic_ct`。読み込める装置
  プロファイルは `python -m app.cli profiles list` で確認します。実在の装置の
  プロファイルの作り方と配置場所は [spec/13](spec/13_device_profiles.md) にあります

## 3. 送信先とワークリストの取得先を設定する

モダリティとして使う前に、`config/app_config.yaml` の `modality:` の節に、
自分の AE タイトル、ワークリストの取得先（RIS）、送信先（PACS）を設定します。
項目の一覧は [spec/12](spec/12_modality_emulator.md) の 12 章にあります。

設定したら、疎通を確認します。

```bash
python -m app.cli echo --to PACS_TEST
python -m app.cli echo --worklist
```

## 4. Web 画面で撮影して送信する

```bash
python -m app.web
python -m app.web --config config/app_config.yaml
```

ブラウザで <http://127.0.0.1:8080/> を開きます。既定ではループバック
（127.0.0.1）だけで待ち受け、認証はありません。

1. ワークリストの画面で「ワークリストを取得」を押し、予約を選んで「選んで撮影へ」を
   押します
2. 撮影の画面で、テンプレート・シリーズ数・画像数を確認し、[撮影して送る] を押します
3. PACS の画面で、送信キューの状態が「送信完了」になったことを確認します。失敗した
   ときは [再送] を押します

予約の無い患者は、ワークリストの画面の [緊急の患者で撮る] から撮影します。画面の
詳細は [spec/12a](spec/12a_web_screens_and_cli.md) の 10 章にあります。

### ネットワークに公開するとき

`web.bind_address` をループバック以外（`0.0.0.0` など）にするときは、HTTP Basic
認証が必須です。パスワードを1行だけ書いたファイルを作成し、環境変数で指定します。
ファイルが無いか空のときは起動しません（終了コード 2）。ユーザー名は `dtg` です。

```bash
DTG_WEB_PASSWORD_FILE=/path/to/password.txt python -m app.web
```

パスワードは設定ファイルに書きません。この画面は HTTPS に対応していないので、
ネットワークに公開するときは、前段のリバースプロキシで TLS を終端してください
（`Host` ヘッダーをそのまま渡す設定にします）。

## 5. CLI で撮影して送信する

Web 画面と同じ操作を CLI でも行えます。自動テストから使うときは `--json` を
付けます。

```bash
# ワークリストを取得し、予約のキーを確認する
python -m app.cli worklist query

# 予約を選んで撮影し、送信する
python -m app.cli exam --from-worklist <キー> -s 2 -i 1,20 --send

# 予約の無い患者で撮影する
python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO"

# 送信キューを確認し、失敗した送信を再送する
python -m app.cli queue list --status failed
python -m app.cli queue retry --all
```

## 6. 保管確認と MPPS を使う

どちらも既定では無効です。設定の項目は [spec/12](spec/12_modality_emulator.md) の
12 章、動作は 8.3・8.4 にあります。

### 保管確認（Storage Commitment）

1. 送信先の `storage_commitment` を `true` にします。結果は相手が別の Association で
   返すことを前提にしています。同じ Association でしか返さない相手のときだけ、
   `commitment_wait_seconds` に秒数を設定します
2. Web 画面を使うときは、送信に成功した画像の保管確認が自動で要求されます。
   PACS の画面の「保管の確認」の列に、確認待ち・確認済・確認の失敗・確認の時間切れ
   のどれかが表示されます
3. CLI では自動で要求しません。送信の後に `commit` で要求し、結果を待ちます。
   確認済なら終了コード 0、それ以外は 5 です。Web 画面が同じポートで待ち受けて
   いるときは、終了コード 2 で停止します

```bash
python -m app.cli queue list               # ジョブの ID と COMMIT の列
python -m app.cli commit --job 1 --wait 60
```

### Orthanc で保管確認をテストする

この手順は、まだ Orthanc を相手に実行して確認していません
（[roadmap.md](roadmap.md)）。

Orthanc（1.6.0 以降）は保管確認を受け付け、結果を別の Association で返します。

1. Orthanc の設定の `DicomModalities` に、DTG の AE タイトル・IP アドレス・待ち受けの
   ポートを追加します（例：`"DicomModalities": { "dtg": [ "DTG_CT01",
   "127.0.0.1", 11113 ] }`）。Orthanc をコンテナで動かすときは、コンテナから到達
   できる IP アドレスを書き、DTG の `listen.bind_address` もそのアドレスで待ち受ける
   ようにします（既定の 127.0.0.1 にはコンテナから到達できません）
2. DTG の送信先を Orthanc の AE タイトル・IP アドレス・DICOM のポートにし、
   `storage_commitment: true` にします
3. `python -m app.web` を起動し、撮影の画面で [撮影して送る] を押します
4. PACS の画面の送信キューで、そのジョブの「保管の確認」が「確認済」になることを
   確認します。CLI では、Web 画面を停止してから
   `python -m app.cli commit --job <ID>` を実行し、`confirmed` と終了コード 0 が
   返ることを確認します

### MPPS

1. ワークリストの取得先の `use_mpps` を `true` にします。送信先を変えるときは
   `modality.mpps:` を設定します（省略するとワークリストの取得先へ送信します）
2. 撮影の開始で N-CREATE（IN PROGRESS）、画像を生成し終えたら N-SET（COMPLETED）を
   送信します。生成の途中で停止したときは N-SET（DISCONTINUED）を送信します
3. MPPS を送信できなくても、撮影と画像の送信は止まりません。撮影の画面と CLI
   （`[WARN] MPPS ...`）に表示され、通知はキューに残ります。残った通知は次の
   コマンドで確認・再送します

```bash
python -m app.cli mpps list
python -m app.cli mpps retry
```

`exam --mpps`・`--no-mpps` で、その撮影だけ設定を上書きできます。Orthanc は MPPS を
受け付けないので、MPPS を受け付けるテスト用の相手（RIS など）を使ってください。
