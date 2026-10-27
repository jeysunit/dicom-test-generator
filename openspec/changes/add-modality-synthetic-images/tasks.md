# Tasks

## 0. 決めること

- [ ] 0.1 proposal の「依頼者が決めること」の 1〜7 の答えを design.md に写し、ADR-0033・
      0034 の本文を答えに合わせる

## 1. 基本の図形（PR 1）

- [ ] 1.1 今の `ct_realistic`・`simple_text` の画素と属性のハッシュを固定する試験を先に書く
- [ ] 1.2 spec 02 の 3 章、03、06 の 4 章、07 の 3.6、12a の CLI に `phantom` を書く
- [ ] 1.3 回転楕円体・位置の目印・焼き込みの帯の試験を `tests/core/` に先に書き、
      `app/core/pixel_generator.py` に図形の評価を足す（ファイルが 800 行を超えるなら
      `app/core/phantom.py` に分ける）
- [ ] 1.4 `PixelSpecPhantom`・設定の `default_pixel_mode`・CLI の `--pixel-mode` に
      `phantom` を足し、CT・MR の画像で Burned In Annotation・Recognizable Visual
      Features・Image Comments を書く
- [ ] 1.5 ADR-0033 を採用にし、usage.md に選び方を書く

## 2. CR・DX（PR 2）

- [ ] 2.1 spec 06 に CR・DX の節を足し、5.2 の「断る」から CR・DX を外す。13 の 4.3 と
      roadmap を直す
- [ ] 2.2 CR Image・DX Image の必須の属性の試験を先に書き、`app/core/generator.py` に
      作る処理を足す。`MONOCHROME1` の試験も書く
- [ ] 2.3 `templates/modality/cr_generic.yaml`・`dx_generic.yaml` と、
      `profiles/examples/dtg_synthetic_cr.yaml`・`dtg_synthetic_dx.yaml` を足す
- [ ] 2.4 CR・DX の予約と緊急の患者を、画面と CLI で撮る試験（`tests/web/`・
      `tests/integration/`）を書く
- [ ] 2.5 CR・DX のテンプレートを断ることを確かめる今の試験があれば、直す前に承認を得る
- [ ] 2.6 見本の画像を dciodvfy で検査し、結果を PR の本文に書く。ADR-0034 を採用にする

## 3. 部位の図形（PR 3）

- [ ] 3.1 ルーチンの `phantom`・`laterality`・`weighting`・`phase` を
      `app/core/routine.py` に足し、`templates/routine/` の付けるルーチンに書く
- [ ] 3.2 部位ごとの図形と、MR の強調・CT の相の値の試験を先に書いて実装する
- [ ] 3.3 開発の環境で、`phantom` で CT 頭部・CT 胸部・MR 頭部・DX 胸部を撮り、試験用の
      PACS のビューアで、スライスを送ると図形が変わること、焼き込みが読めることを確かめる
- [ ] 3.4 `pytest`・markdownlint・`check_doc_dates.py` が合格することを確かめ、この
      change を archive する
