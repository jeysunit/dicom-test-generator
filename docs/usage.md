# 使い方

DTG を Web 画面で使う手順を、操作の順に説明する。CLI で同じことをする方法と、
CLI だけでできることは 6・7 章にまとめる。コマンドのオプションと設定の項目の
一覧は spec にある（CLI は [spec/04](spec/04_cli.md) と
[spec/12a](spec/12a_web_screens_and_cli.md) の 11 章、設定は
[spec/12](spec/12_modality_emulator.md) の 12 章、Job YAML は
[spec/07](spec/07_job_schema.md)）。

本番の PACS には送信せず、テスト用の PACS・RIS にだけ接続する。

## 1. 起動する

### 1.1 Docker で起動する

`Dockerfile` で、CLI と Web 画面のイメージをビルドできる。コンテナは root 以外のユーザー（uid 10001）で動作する。

```bash
docker build -t dicom-test-generator .
```

設定ファイルとパスワードのファイルはリポジトリの外（例：`~/dtg/`）に置き、
コンテナにマウントする。コンテナの中では Web 画面が `0.0.0.0` にバインドするので、
設定の `web.bind_address` を `"0.0.0.0"` にし、パスワードのファイルを渡す
（5.3 節）。次の例は、ポートをホストの 127.0.0.1 にだけ公開する。

```bash
docker run -d --name dtg -p 127.0.0.1:8080:8080 \
  -v "$HOME/dtg/app_config.yaml:/app/config/app_config.yaml:ro" \
  -v "$HOME/dtg/password.txt:/run/secrets/dtg_web_password:ro" \
  -e DTG_WEB_PASSWORD_FILE=/run/secrets/dtg_web_password \
  -v dtg-state:/app/modality_state -v "$HOME/dtg/output:/app/output" \
  dicom-test-generator
```

- 作成した DICOM ファイルは `/app/output` に、予約の結果と送信キューは
  `/app/modality_state` に書き出す。残すときはマウントする
- パスワードのファイルと、バインドマウントするホストのディレクトリは、uid 10001 が
  読み書きできるようにする（例：`chmod 0644`）
- イメージにヘルスチェックは入れていない

ブラウザで <http://127.0.0.1:8080/> を開き、ユーザー名 `dtg` とパスワードで
ログインする。

### 1.2 Python で起動する

Python 3.10 以上で、リポジトリのディレクトリで実行する。

```bash
pip install -r requirements.txt
python -m app.web
```

既定ではループバック（127.0.0.1）だけで待ち受け、認証は無い。ブラウザで
<http://127.0.0.1:8080/> を開く。

## 2. Web 画面で撮影する

### 2.1 予約から撮影する

1. ワークリストの画面で、予定日・モダリティ・AE タイトルを選び、「ワークリストを取得」を
   押す
2. 一覧から予約を選び、「選んで撮影へ」を押す
3. 撮影の画面で、予約の値（読み取り専用）を確認し、テンプレート・シリーズ数・
   画像数・異常のデータを選ぶ
4. [撮影して送る] を押す。DICOM ファイルを作成して出力フォルダに保存し、続けて
   既定の送信先（PACS）へ送信する。送信しないときは [撮影] を押す

作成した DICOM ファイルは、出力フォルダの
`<受付番号か emergency>_<撮影の日時 YYYYMMDDHHMMSS>/` に保存される（既定の
出力フォルダは `output/modality`、Docker では `/app/output` の下）。

予約で1回撮影すると、その予約は撮影済みになり、[撮影]・[撮影して送る] は押せなく
なる（一覧にも「撮影済み」の印が付く）。撮り直すときは、設定の `retake_mode` に従う。

- `append`（既定）：[追加撮影] で、同じ Study に新しいシリーズとして撮る（IHE の
  Append Case）。CLI では `exam --from-worklist <鍵> --append`
- `new_order`：RIS で撮り直しの予約を作り、ワークリストを取得し直して、その予約で
  撮る（受付番号と Study Instance UID は RIS が出す）

### 2.2 予約の無い患者で撮影する

ワークリストの画面の [緊急の患者で撮る] を押し、撮影の画面で患者 ID と氏名（英字）を
入力する。氏名の姓と名は空白で区切って入力する（DICOM の区切りの `^` に置き換える）。
あとは 2.1 の 3・4 と同じ。

画面の項目と表示は [spec/12a](spec/12a_web_screens_and_cli.md) の 10 章にある。

## 3. 送信の状態を確認し、再送する

PACS の画面の送信キューに、ジョブごとの状態（待機中・送信中・送信完了・送信失敗）が
表示される。

- 送信失敗の行は、理由が表示される。[再送] で再送し、表の上の [失敗をすべて再送] で
  失敗したジョブをまとめて再送する
- 送信完了の行の [再送] と、撮影の画面の送信の結果の下の [もう一度送る] で、同じ画像を
  何回でも送り直せる。送るたびに新しいジョブになり、画像の UID は変わらない
- 行の [詳細] で、元のファイル（出力フォルダ）・試行回数・名乗る AE タイトルが
  浮かぶ枠に出る。枠の外を押すか Esc で閉じる
- 送信先の一覧の [C-ECHO] で、送信先との疎通を確認できる

## 4. 保管確認（Storage Commitment）と MPPS を使う

どちらも既定では無効。設定の項目は [spec/12](spec/12_modality_emulator.md) の
12 章、動作は 8.3・8.4 にある。

### 4.1 保管確認

1. 送信先の `storage_commitment` を `true` にする。結果は相手が別の Association で
   返すことを前提にしている。同じ Association でしか返さない相手のときだけ、
   `commitment_wait_seconds` に秒数を設定する
2. 送信に成功した画像の保管確認が自動で要求される。PACS の画面の「保管の確認」の
   列に、確認待ち・確認済・確認の失敗・確認の時間切れのどれかが表示される
3. Docker で動かすときは、設定の `modality.listen.bind_address` を `"0.0.0.0"` にし、
   待ち受けのポート（既定 11113）も公開する

### 4.2 Orthanc で保管確認をテストする

この手順は、まだ Orthanc を相手に実行して確認していない（[roadmap.md](roadmap.md)）。
Orthanc（1.6.0 以降）は保管確認を受け付け、結果を別の Association で返す。

1. Orthanc の設定の `DicomModalities` に、DTG の AE タイトル・IP アドレス・待ち受けの
   ポートを追加する（例：`"DicomModalities": { "dtg": [ "DTG_CT01",
   "127.0.0.1", 11113 ] }`）。Orthanc をコンテナで動かすときは、コンテナから到達
   できる IP アドレスを書き、DTG の `listen.bind_address` もそのアドレスで待ち受ける
   ようにする（既定の 127.0.0.1 にはコンテナから到達できない）
2. DTG の送信先を Orthanc の AE タイトル・IP アドレス・DICOM のポートにし、
   `storage_commitment: true` にする
3. 撮影の画面で [撮影して送る] を押す
4. PACS の画面の送信キューで、そのジョブの「保管の確認」が「確認済」になることを
   確認する

### 4.3 MPPS

1. ワークリストの取得先の `use_mpps` を `true` にする。送信先を変えるときは
   `modality.mpps:` を設定する（省略するとワークリストの取得先へ送信する）
2. 撮影の開始で N-CREATE（IN PROGRESS）、画像を作成し終えたら N-SET（COMPLETED）を
   送信する。作成の途中で停止したときは N-SET（DISCONTINUED）を送信する
3. MPPS を送信できなくても、撮影と画像の送信は止まらない。撮影の画面に表示され、
   通知はキューに残る。残った通知は CLI の `mpps retry` で再送する（6 章）

Orthanc は MPPS を受け付けないので、MPPS を受け付けるテスト用の相手（RIS など）を
使う。

## 5. 設定を変更する

### 5.1 送信先とワークリストの取得先

`config/app_config.yaml` の `modality:` の節に、名乗る装置（`stations`）、ワークリストの
取得先（RIS）、送信先（PACS）を設定し、画面を再起動する。設定の画面は読み取り専用で、
読み込んだ値を確認できる。Docker で動かすときは、コンテナから到達できるホスト名か
IP アドレスを設定する。項目の一覧は [spec/12](spec/12_modality_emulator.md) の
12 章にある。

### 5.2 装置を切り替える

装置を2台以上設定すると（例 CT1 は `DTG_CT01`、MR1 は `DTG_MR01`）、情報バーの
「装置」で切り替えられる。切り替えた装置の AE タイトルで、ワークリストの取得・送信・
MPPS・保管確認を行い、画像の Station Name もその装置の値になる。選んだ装置は画面を
再起動しても残り、CLI も同じ装置を使う（`--station <表示名>` でそのコマンドだけ
変えられる）。

- PACS・RIS には、使う装置の AE タイトルをすべて登録しておく。登録していない AE
  タイトルで断られると、「相手が AE タイトル DTG_MR01 を受け付けませんでした」と出る
- 切り替える前に作った送信の件と MPPS は、再送しても作ったときの AE タイトルで送る

### 5.3 ネットワークに公開する

`web.bind_address` をループバック以外（`0.0.0.0` など）にするときは、HTTP Basic
認証が必須。パスワードを1行だけ書いたファイルを作成し、環境変数で指定する。
ファイルが無いか空のときは起動しない（終了コード 2）。ユーザー名は `dtg`。

```bash
DTG_WEB_PASSWORD_FILE=/path/to/password.txt python -m app.web
```

パスワードは設定ファイルに書かない。この画面は HTTPS に対応していないので、
ネットワークに公開するときは、前段のリバースプロキシで TLS を終端する
（`Host` ヘッダーをそのまま渡す設定にする）。

## 6. CLI で同じ操作をする

2〜4 章の操作は CLI でも行える。自動テストから使うときは `--json` を付ける。
Docker で動かしているときは、`docker exec dtg python -m app.cli ...` で実行する。

| 操作 | コマンド |
|------|----------|
| 疎通の確認 | `python -m app.cli echo --to PACS_TEST`・`echo --worklist` |
| ワークリストの取得 | `python -m app.cli worklist query` |
| 予約から撮影して送信 | `python -m app.cli exam --from-worklist <キー> -s 2 -i 1,20 --send` |
| 予約の無い患者で撮影 | `python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO"` |
| 送信キューの確認と再送 | `python -m app.cli queue list --status failed`・`queue retry --all` |
| 保管確認の要求 | `python -m app.cli commit --job 1 --wait 60` |
| MPPS の確認と再送 | `python -m app.cli mpps list`・`mpps retry` |

- CLI では保管確認を自動で要求しない。送信の後に `commit` で要求して結果を待つ。
  確認済なら終了コード 0、それ以外は 5。Web 画面が同じポートで待ち受けているときは、
  終了コード 2 で停止する
- `exam --mpps`・`--no-mpps` で、その撮影だけ MPPS の設定を上書きできる

## 7. CLI だけでできること

Web 画面に無い、細かい条件での作成は CLI で行う。

```bash
# Job YAML の設定を検証する（作成しない）
python -m app.cli validate examples/job_minimal.yaml

# Job YAML から作成する
python -m app.cli generate examples/job_full.yaml -o output/

# 引数だけで作成する
python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o output/
```

- Job YAML には、患者・検査・シリーズ・ピクセル・Transfer Syntax・文字コードを
  細かく書ける。`examples/` に、最小の例（`job_minimal.yaml`）とすべての項目を
  書いた例（`job_full.yaml`）がある
- 異常のデータを作成する：`--abnormal-level mild`（`none`・`mild`・`moderate`・
  `severe`）。指定しなければ規格どおりのデータを作成する
- 装置プロファイルを重ねる：`--profile dtg_synthetic_ct`。読み込める装置
  プロファイルは `python -m app.cli profiles list` で確認する。実在の装置の
  プロファイルの作り方と配置場所は [spec/13](spec/13_device_profiles.md) にある
