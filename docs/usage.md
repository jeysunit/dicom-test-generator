# 使い方

DTG を Web 画面で使う手順を、操作の順に説明する。CLI で同じことをする方法と、
CLI だけでできることは 6・7 章にまとめる。コマンドのオプションと設定の項目の
一覧は spec にある（CLI は [spec/04](spec/04_cli.md) と
[spec/12a](spec/12a_web_screens_and_cli.md) の 11 章、設定は
[spec/12](spec/12_modality_emulator.md) の 12 章、Job YAML は
[spec/07](spec/07_job_schema.md)）。

本番の PACS には送信せず、テスト用の PACS・RIS にだけ接続する。

## 1. 起動する

DTG は Docker のイメージ `ghcr.io/jeysunit/dicom-test-generator` で動かす。
Python の環境で動かす方法は、開発する人向けに
[development.md](development.md) の 1 章にある。

### 1.1 Web 画面を起動する

コンテナの中の Web 画面はすべてのアドレスで待ち受けるので、パスワードが必須になる。
作業用のフォルダ（例：`~/dtg/`）に、パスワードを1行だけ書いたファイル
`password.txt` と、出力フォルダ `output/` を作り、そのフォルダで実行する。次の例は、
ポートをホストの 127.0.0.1 にだけ公開する。

```bash
mkdir -p output
docker run -d --name dtg --user "$(id -u):$(id -g)" -p 127.0.0.1:8080:8080 \
  -v "$PWD/password.txt:/run/secrets/dtg_web_password:ro" \
  -e DTG_WEB_PASSWORD_FILE=/run/secrets/dtg_web_password \
  -v "$PWD/output:/app/output" -v dtg-state:/app/modality_state \
  ghcr.io/jeysunit/dicom-test-generator:latest
```

ブラウザで <http://127.0.0.1:8080/> を開き、ユーザー名 `dtg` とパスワードで
ログインする。

- 作成した DICOM ファイルは `/app/output` に、予約の結果と送信キューは
  `/app/modality_state` に書き出す。上の例は、出力をホストの `output/` に、予約の
  結果と送信キューを名前付きボリューム `dtg-state` に残す
- `--user "$(id -u):$(id -g)"` を付けると、作成したファイルの所有者がホストの
  利用者になる。付けないときは、コンテナは uid 10001 で動く
- パスワードのファイルが無いか空なら、コンテナは起動しない（終了コード 2）
- 送信先を設定するときは、設定ファイルを `/app/config/app_config.yaml` にマウント
  する（5.1 節）
- イメージにヘルスチェックは入れていない

### 1.2 イメージをビルドする

リポジトリの `Dockerfile` から、同じイメージをビルドできる。イメージが
まだ公開されていないとき（最初のタグの push の前）は、ビルドしたイメージの名前を
1.1 の `ghcr.io/jeysunit/dicom-test-generator:latest` の代わりに使う。

```bash
docker build -t dicom-test-generator .
```

## 2. Web 画面で撮影する

### 2.1 予約から撮影する

1. ワークリストの画面で、予定日・モダリティ・AEタイトルを選び、「ワークリスト検索」を
   押す
2. 一覧から予約を選び、「選んで撮影へ」を押す
3. 撮影の画面で、予約の値（読み取り専用）を確認する。「ルーチン」には、予約の検査の
   記述（胸部・頭部・腹部など）に合うルーチンが選ばれ、シリーズの並びと画像数が
   入っている。そのまま撮れる。変えるときは、ルーチンを選び直すか、画像数を直すか、
   [外す] でシリーズを外す。外したシリーズは薄く表示され、[戻す] で元の画像数のまま
   戻せる。「手で入れる」を選ぶと、シリーズ数と画像数を入れる欄になる
4. [撮影して送信] を押す。DICOM ファイルを作成して出力フォルダに保存し、続けて
   標準の送信先（PACS）へ送信する。送信しないときは [撮影] を押す

作成した DICOM ファイルは、出力フォルダの
`<受付番号か emergency>_<撮影の日時 YYYYMMDDHHMMSS>/` に保存される（出力
フォルダは設定の `output_dir` で、初期設定は `output/modality`。1.1 の例では、ホストの
`output/modality/` の下になる）。

予約で1回撮影すると、その予約は撮影済みになり、[撮影]・[撮影して送信] は押せなく
なる（一覧にも「撮影済み」の印が付く）。撮り直すときは、設定の `retake_mode` に従う。

- `append`（初期設定）：[追加撮影] で、同じ Study に新しいシリーズとして撮る（IHE の
  Append Case）。CLI では `exam --from-worklist <鍵> --append`
- `new_order`：RIS で撮り直しの予約を作り、ワークリストを再検索して、その予約で
  撮る（受付番号と Study Instance UID は RIS が出す）

### 2.2 予約の無い患者で撮影する

ワークリストの画面の [緊急の患者で撮る] を押し、撮影の画面で患者ID・氏名（漢字）・性別を
入力する。氏名の姓と名は空白で区切って入力する（DICOM の区切りの `^` に置き換える）。
あとは 2.1 の 3・4 と同じ。

身元が分からない患者は、[仮の ID を作る] で患者ID（既定は `TMP` と日時の番号）を作り、
「氏名が分からない」を選ぶ（氏名は漢字「不明 不明」・かな「フメイ フメイ」、英字は空）。
性別が分からなければ「その他」を選ぶ。頭と氏名は設定の `temporary_patient_id_prefix`・
`unknown_name_ideographic`・`unknown_name_phonetic` で変えられる
（[spec/12](spec/12_modality_emulator.md) の 12 章）。撮った後に RIS が MPPS の仮の患者を
正式な患者に統合する流れ（IHE PIR の Case 6）の試験に使える。

画面の項目と表示は [spec/12a](spec/12a_web_screens_and_cli.md) の 10 章にある。

## 3. 送信の状態を確認し、再送信する

PACS の画面の下の段（送信ジョブ）に、ジョブごとの状態（送信待ち・送信中・送信完了・送信失敗）が
表示される。上の段には送信先が並ぶ。状態ごとの件数のボタンと、期間・送信先・患者ID の
検索の帯で、一覧を絞れる。

- 送信失敗の行は、理由が表示される。[もう一度送る] で再送信し、見出しの右の
  [失敗 n 件を再送信] で失敗したジョブをまとめて再送信する（確認の窓で [再送信する] を
  押すまで送らない）
- 送信完了の行の [もう一度送る] と、撮影の画面の送信の結果の下の [もう一度送る] で、同じ画像を
  何回でも送り直せる。送るたびに新しいジョブになり、画像の UID は変わらない
- 行の [詳細] で、その行を選ぶと、一覧の下に元のファイル（出力フォルダ）・試行回数・
  名乗る AEタイトルなどの詳細が出る。[閉じる] で閉じる
- 接続先の一覧の [接続確認]（C-ECHO）で、送信先とワークリストの取得先との疎通を確認できる。
  [すべて接続確認] と、上の帯の接続の状態の中身の [接続確認] は、全部の相手をまとめて確かめる

## 4. 保管確認（Storage Commitment）と MPPS を使う

どちらも初期設定では無効。設定の項目は [spec/12](spec/12_modality_emulator.md) の
12 章、動作は 8.3・8.4 にある。

### 4.1 保管確認

1. 送信先の `storage_commitment` を `true` にする。結果は相手が別の Association で
   返すことを前提にしている。同じ Association でしか返さない相手のときだけ、
   `commitment_wait_seconds` に秒数を設定する
2. 送信に成功した画像の保管確認が自動で要求される。PACS の画面の「保管の確認」の
   列に、確認待ち・確認済・確認の失敗・確認の時間切れのどれかが表示される
3. Docker で動かすときは、設定の `modality.listen.bind_address` を `"0.0.0.0"` にし、
   待ち受けのポート（初期設定 11113）も公開する

### 4.2 Orthanc で保管確認をテストする

この手順は、まだ Orthanc を相手に実行して確認していない（[roadmap.md](roadmap.md)）。
Orthanc（1.6.0 以降）は保管確認を受け付け、結果を別の Association で返す。

1. Orthanc の設定の `DicomModalities` に、DTG の AEタイトル・IP アドレス・待ち受けの
   ポートを追加する（例：`"DicomModalities": { "dtg": [ "DTG_CT01",
   "127.0.0.1", 11113 ] }`）。Orthanc をコンテナで動かすときは、コンテナから到達
   できる IP アドレスを書き、DTG の `listen.bind_address` もそのアドレスで待ち受ける
   ようにする（初期設定の 127.0.0.1 にはコンテナから到達できない）
2. DTG の送信先を Orthanc の AEタイトル・IP アドレス・DICOM のポートにし、
   `storage_commitment: true` にする
3. 撮影の画面で [撮影して送信] を押す
4. PACS の画面の送信キューで、そのジョブの「保管の確認」が「確認済」になることを
   確認する

### 4.3 MPPS

1. ワークリストの取得先の `use_mpps` を `true` にする。送信先を変えるときは
   `modality.mpps:` を設定する（省略するとワークリストの取得先へ送信する）
2. 撮影の開始で N-CREATE（IN PROGRESS）、画像を作成し終えたら N-SET（COMPLETED）を
   送信する。作成の途中で停止したときは N-SET（DISCONTINUED）を送信する
3. MPPS を送信できなくても、撮影と画像の送信は止まらない。撮影の画面に表示され、
   通知はキューに残る。残った通知は CLI の `mpps retry` で再送信する（6 章）

Orthanc は MPPS を受け付けないので、MPPS を受け付けるテスト用の相手（RIS など）を
使う。

## 5. 設定を変更する

### 5.1 送信先とワークリストの取得先

設定ファイルの `modality:` の節に、名乗る装置（`stations`）、ワークリストの取得先
（RIS）、送信先（PACS）を設定し、コンテナを起動し直す。ホスト名と IP アドレスは、コンテナから
到達できるものを書く。設定の画面は読み取り専用で、読み込んだ値を確認できる。項目の
一覧は [spec/12](spec/12_modality_emulator.md) の 12 章にある。

イメージの中の設定ファイルを取り出して編集し、`/app/config/app_config.yaml` に
マウントする。取り出した設定は、Web 画面がすべてのアドレスで待ち受ける形
（`web.bind_address: "0.0.0.0"`）になっている。

```bash
docker run --rm ghcr.io/jeysunit/dicom-test-generator:latest cat config/app_config.yaml > app_config.yaml
```

1.1 の `docker run` に
`-v "$PWD/app_config.yaml:/app/config/app_config.yaml:ro"` を追加して起動する。

### 5.2 装置を切り替える

装置を2台以上設定すると（例 CT1 は `DTG_CT01`、MR1 は `DTG_MR01`）、上の帯の
「接続の状態」を開いた中の「装置」で切り替えられる。切り替えた装置の AEタイトルで、ワークリストの取得・送信・
MPPS・保管確認を行い、画像の Station Name もその装置の値になる。選んだ装置は画面を
再起動しても残り、CLI も同じ装置を使う（`--station <表示名>` でそのコマンドだけ
変えられる）。

- PACS・RIS には、使う装置の AEタイトルをすべて登録しておく。登録していない AE
  タイトルで断られると、「相手が AEタイトル DTG_MR01 を受け付けませんでした」と出る
- 切り替える前に作った送信の件と MPPS は、再送信しても作ったときの AEタイトルで送る

### 5.3 ネットワークに公開する

1.1 の例は、ポートをホストの 127.0.0.1 にだけ公開している。ほかのマシンから
開くときは、`-p 8080:8080` のようにホストのすべてのアドレスに公開する。コンテナの
Web 画面は HTTP Basic 認証が必須で（ユーザー名は `dtg`）、パスワードは環境変数
`DTG_WEB_PASSWORD_FILE` で指定したファイルから読む。パスワードは設定ファイルに
書かない。

この画面は HTTPS に対応していないので、ネットワークに公開するときは、前段の
リバースプロキシで TLS を終端する（`Host` ヘッダーをそのまま渡す設定にする）。

## 6. CLI で同じ操作をする

2〜4 章の操作は CLI でも行える。1.1 で起動したコンテナの中で、表のコマンドを
`docker exec dtg` に続けて実行する（例：`docker exec dtg python -m app.cli worklist query`）。
自動テストから使うときは `--json` を付ける。

| 操作 | コマンド |
|------|----------|
| 疎通の確認 | `python -m app.cli echo --to PACS_TEST`・`echo --worklist` |
| ワークリストの取得 | `python -m app.cli worklist query` |
| 予約から撮影して送信（予約に当てたルーチン） | `python -m app.cli exam --from-worklist <キー> --send` |
| ルーチンを選んで撮影 | `python -m app.cli exam --from-worklist <キー> --routine ct_head_plain` |
| シリーズ数と画像数を手で入れて撮影 | `python -m app.cli exam --from-worklist <キー> -s 2 -i 1,20` |
| 予約の無い患者で撮影 | `python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO"` |
| 予約の無い患者の検査に追加で撮影（前の撮影と同じ患者ID・氏名） | `python -m app.cli exam --emergency --append --study-uid <前の撮影の Study Instance UID> --patient-id E0001 --patient-name "KINKYU^TARO"` |
| 送信キューの確認と再送信 | `python -m app.cli queue list --status failed`・`queue retry --all` |
| 保管確認の要求 | `python -m app.cli commit --job 1 --wait 60` |
| MPPS の確認と再送信 | `python -m app.cli mpps list`・`mpps retry` |

- CLI では保管確認を自動で要求しない。送信の後に `commit` で要求して結果を待つ。
  確認済なら終了コード 0、それ以外は 5。Web 画面が同じポートで待ち受けているときは、
  終了コード 2 で停止する
- `exam --mpps`・`--no-mpps` で、その撮影だけ MPPS の設定を上書きできる
- 撮影のルーチンは `templates/routine/` の YAML（CT・MR・CR・DX・US の部位ごと）。
  施設のルーチンは同じ形の YAML を足して作る。MR・CR・DX・US のルーチンは、それらの
  画像を作れるようになるまで使えない

## 7. CLI だけでできること

Web 画面に無い、細かい条件での作成は CLI で行う。Web 画面を起動していなくても、
`docker run --rm` でコマンドだけを実行できる。次の例は、作業用のフォルダの
`output/` に書き出す。

```bash
mkdir -p output
IMAGE=ghcr.io/jeysunit/dicom-test-generator:latest
dtg() { docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/output:/app/output" "$@"; }

# 引数だけで作成する
dtg "$IMAGE" python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o /app/output

# イメージの中の Job YAML の例を検証する（作成しない）・例から作成する
dtg "$IMAGE" python -m app.cli validate examples/job_minimal.yaml
dtg "$IMAGE" python -m app.cli generate examples/job_full.yaml -o /app/output

# 手元の Job YAML から作成する
dtg -v "$PWD/job.yaml:/app/job.yaml:ro" "$IMAGE" python -m app.cli generate /app/job.yaml -o /app/output
```

- Job YAML には、患者・検査・シリーズ・ピクセル・Transfer Syntax・文字コードを
  細かく書ける。イメージの `examples/` に、最小の例（`job_minimal.yaml`）とすべての
  項目を書いた例（`job_full.yaml`）がある
- 異常のデータを作成する：`--abnormal-level mild`（`none`・`mild`・`moderate`・
  `severe`）。指定しなければ規格どおりのデータを作成する
- 装置プロファイルを重ねる：`--profile dtg_synthetic_ct`。読み込める装置
  プロファイルは `python -m app.cli profiles list` で確認する。実在の装置の
  プロファイルの作り方と配置場所は [spec/13](spec/13_device_profiles.md) にある
