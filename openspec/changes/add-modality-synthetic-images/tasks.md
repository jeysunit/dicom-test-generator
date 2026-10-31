# Tasks

## 0. 決めること

- [x] 0.1 proposal の「決めたこと」の 1〜8 の答えを design.md に写し、ADR-0033・
      0034 の本文を答えに合わせる（2026-10-27）

## 1. 基本の図形（PR 1）

- [ ] 1.1 今の `ct_realistic`・`simple_text` の画素と属性のハッシュを固定する試験を先に書く
- [ ] 1.2 spec 02 の 3 章、03、06 の 4 章、07 の 3.6、12a の CLI に `phantom` を書く
- [ ] 1.3 回転楕円体・位置の目印の試験を `tests/core/` に先に書き、
      `app/core/pixel_generator.py` に図形の評価を足す（ファイルが 800 行を超えるなら
      `app/core/phantom.py` に分ける）
- [ ] 1.4 図形を撮影ごとに一度だけ決めることと、`phantom` のときの冠状断・矢状断の
      位置の試験を先に書き、`app/core/series_layout.py` と
      `app/services/study_generator.py` に入れる。ほかの方式の位置が変わらないことも
      確かめる
- [ ] 1.5 `PixelSpecPhantom`・設定の `default_pixel_mode`・CLI の `--pixel-mode` に
      `phantom` を足し、CT・MR の画像に偽物の印（Manufacturer・Manufacturer's Model
      Name `DTG SYNTHETIC`、Image Comments `SYNTHETIC TEST DATA`、Burned In
      Annotation `NO`、Recognizable Visual Features `NO`）を、装置のプロファイルの
      後に書く
- [ ] 1.6 ADR-0033 を採用にし、usage.md に選び方を書く

## 2. CR・DX（PR 2）

- [x] 2.1 spec 06 に CR・DX の節を足し、5.2 の「断る」から CR・DX を外す。13 の 4.3 と
      roadmap を直す
- [x] 2.2 CR Image・DX Image の必須の属性の試験を先に書き、`app/core/generator.py` に
      作る処理を足す。`MONOCHROME1` の試験も書く（モジュールの値は
      `app/core/projection.py` に分けた）
- [x] 2.3 CR・DX のルーチンの `body_part`・`laterality` と、その検証（CR の `B`、
      対になる部位の省略、対にならない部位の左右を断る）を試験を先に書いて足し、
      `templates/routine/` の `cr_*`・`dx_*` に書く
- [x] 2.4 `templates/modality/cr_generic.yaml`・`dx_generic.yaml` と、
      `profiles/examples/dtg_synthetic_cr.yaml`・`dtg_synthetic_dx.yaml` を足す
- [x] 2.5 CR・DX の予約と緊急の患者を、画面と CLI で撮る試験（`tests/web/`・
      `tests/integration/`）を書く
- [x] 2.6 CR・DX のテンプレートを断ることを確かめる今の試験があれば、直す前に承認を得る
      （該当する試験は無かった）
- [ ] 2.7 見本の画像を dciodvfy で検査し、結果を PR の本文に書く。そのうえで
      ADR-0034 を採用にする
      （dciodvfy は手元に無く、PR 2 では検査していない。dciodvfy の検査の後に
      採用にする。未実施）

## 3. 部位の図形（PR 3）

- [x] 3.1 ルーチンの `phantom`・`weighting`・`phase` を
      `app/core/routine.py` に足し、`templates/routine/` の付けるルーチンに書く
- [x] 3.2 部位ごとの図形と、MR の強調・CT の相の値の試験を先に書いて実装する
      （図形は `app/core/phantom_region.py` に分けた。spec/06 の 4.7）
- [x] 3.3 開発の環境で、`phantom` で CT 頭部・CT 胸部・MR 頭部・DX 胸部を撮り、
      送った DICOM ファイルを読んで、スライスごとに画素が変わること・偽物の印のタグ
      〔Manufacturer・Image Comments・Burned In Annotation `NO`〕を確かめる
      （2026-10-31。Orthanc へ4件とも送信できた）
- [ ] 3.4 試験用の PACS のビューアで、スライスを送ると図形が変わること、偽物の印の
      タグが見えることを確かめる（Orthanc のビューアは認証があり、未確認）

## 4. 焼き込み（PR 4）

- [ ] 4.1 spec 02 の 3 章、06 の 4 章、07 の 3.6、12a の CLI に焼き込み（`burn_in`）を書く
- [ ] 4.2 帯・ASCII 以外の字・Burned In Annotation `YES`・`phantom` 以外との組み合わせを
      断る試験・CLI と設定の優先の順の試験を先に書き、Job の `pixel_spec.burn_in`・
      CLI の `--burn-in`・`--no-burn-in`・設定の `modality.burn_in` を足す

## 5. 仕上げ

- [ ] 5.1 `pytest`・markdownlint・`check_doc_dates.py` が合格することを確かめ、この
      change を archive する
