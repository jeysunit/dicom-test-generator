# ADR-0011: モダリティエミュレーターにする（SCU・Web 画面）

- 状態：採用
- 作成日：2026-10-18
- 最終更新日：2026-10-22

## 背景

このツールは DICOM のファイルを生成するところまでで、生成した画像を PACS へ
登録するには別のツールが必要になる。PACS・RIS のテストでは、次の流れを
繰り返し実行したい。

```text
ワークリストを取得 → 予約を選択 → 予約の値で撮影 → PACS へ送信 → 確認
```

本物のモダリティを使わずにこれを実行するには、このツールが「モダリティの
役」を持つ必要がある。画面が無いと、モダリティエミュレーターとして
機能が足りない（技師の操作の流れを再現できない）。

### 要求

- ワークリスト（C-FIND MWL）の SCU、C-STORE・C-ECHO の SCU
- 保管確認（Storage Commitment）・MPPS は選択できる形
- 予約の値を画像に正しく転記する（IHE Scheduled Workflow）
- 画面：ワークリスト・撮影・PACS・設定。PACS の画面と統一感のある形
- 同じ操作を CLI でも行え、自動テストから使える
- 本番の PACS に接続せずにテストできる

## 決定

1. **このツールをモダリティエミュレーターに拡張する。** 仕様は
   [spec/12_modality_emulator.md](../spec/12_modality_emulator.md)
2. **SCU の通信と手順を `app/modality/` に分け、Service Layer の
   一部として扱う。** 予約から生成の設定への転記は Pure な処理として
   `app/core/` に置く
3. **保管確認と MPPS は、送信先・相手ごとに選択できる形にし、既定は
   使わない。**
4. **モダリティの画面は Web 画面にする（サーバー側で描画する。
   FastAPI・Jinja2・HTMX・Tailwind CSS）。** モダリティの画面について、
   ADR-0003（PySide6）を置き換える。見た目の値（色・文字・部品の形）は
   PACS の画面と同じにし、ライトテーマを既定・ダークテーマに切り替えられる
   形にする。画面はすっきりさせ、機能は追加するより減らす（2026-10-18 に
   追加した方針。テスト用のスタブなので機能は少なくてよい。
   spec/12a の 10 章の冒頭）
5. **画面の待ち受けは既定でループバック（127.0.0.1）だけ。** それ以外の
   アドレスで待ち受けるときは簡単な認証（HTTP Basic）を必須にする

### 理由

#### 1. モダリティエミュレーターにする理由

- テストで必要なのは「ファイル」より「装置としての振る舞い」
  （予約を取得する・値を転記する・送信する・確認する）
- 予約の値の転記（Study Instance UID・受付番号・Request Attributes
  Sequence など）は、PACS・RIS の連携の不具合が出やすい所で、
  ここを正しく、または意図的に崩して実行できることにテストの価値がある
- 既存の生成の処理（テンプレート・異常のデータ・ピクセル）を
  そのまま使える

#### 2. `app/modality/` に分ける理由

- `app/services/` は生成の処理（ファイルを生成する）、`app/modality/` は
  通信と手順（相手とやり取りする）で、壊れ方とテストのツールが違う
  （通信のテストは、テストの中でスタブの SCP をローカルに起動する）
- CLI と Web 画面の両方から同じ手順を使う。UI に手順を書くと
  2か所に分かれる
- 当時は `app/scp/`（受信側）と互いに import しない形にして、並べて
  「撮影→送信→受信」の閉じたテストにできるとした。2026-10-20 に受信側を
  削除した（[ADR-0013](0013-remove-storage-scp.md)）。テストの受信側は、テストの中の
  スタブ（`tests/modality_peers.py`）
- 転記の処理を `app/core/` に置くと、通信なしで単体テストができる
  （ADR-0001 の Core-First と同じ考え）

#### 3. MPPS と保管確認を選択できる形にする理由

- Orthanc は MPPS（N-CREATE・N-SET）を受け付けない。DICOM Conformance
  Summary に無く、ソース（`CommandDispatcher.cpp`）も扱わない
  DIMSE として拒否する。MPPS を必須にすると、主なテスト相手で流れが
  止まる
- 保管確認は Orthanc 1.6.0 から受け付けるが、相手に要求元の
  モダリティの登録が必要で、結果は別の Association で非同期に来る。
  使わないテストも多い
- 実際の装置でも、どちらも設定で無効にすることが多い

#### 4. 画面を Web にする理由（PySide6 にしない理由）

- PACS の画面（Web 画面）と統一感のある形にする
  要望がある。同じ色・文字・部品の形を、Tailwind CSS の同じ値で作成できる
- ブラウザがあればどの OS でも開け、PySide6（大きなパッケージ）をインストール
  せずに済む。テスト用の機材の上で動かし、ローカルの PC のブラウザから見る
  使い方にも合う
- FastAPI の TestClient で、画面の応答を pytest のままテストできる
- サーバー側で描画するので、core・services をそのまま呼べる。Node の
  ビルドは不要（Tailwind CSS の standalone の実行ファイルで CSS を
  生成し、生成した CSS を commit する）

#### (b) Next.js＋Python の API を選ばない理由

- 型とテストを2つの言語で持つことになり、保守の手間と CI の処理が増える
- Node の依存が数百のパッケージになる
- 統一感は見た目の値をそろえれば得られる。React の部品そのものを
  共有する必要は今は無い
- 将来、色・文字の値（design tokens）を1か所に持てば、両方から同じ値を
  使える（spec/12a の 10.1）

#### 5. 既定でループバックだけにする理由

- テスト用のツールで、患者の値は合成でも、ネットワークに公開すると誰でも撮影・
  送信を実行できる
- 利用者の管理や監査の記録は、このツールの目的ではない
  （PACS の画面とは目的が違う）。ループバック以外で待ち受けるときだけ最小の
  認証を求め、パスワードが無ければ起動しない（安全を既定にする）

## 既存の PySide6 の GUI の扱い（案 B に決まった。2026-10-18）

| 案 | 内容 | 良い点 | 悪い点 |
|----|------|--------|--------|
| A. 残す | 生成用のツールの画面として残し、保守を続ける。Phase 2b（GUI のフル機能）は進めない | 今の利用者の使い方が変わらない | 画面が2種類になり、同じ機能を2回作る誘因になる |
| **B. 後で削除する（採用）** | Phase 3b で Web 画面が生成の機能（今の PySide6 の画面と同じ範囲）も持てたら、別の PR で `app/gui/`・PySide6・pytest-qt を削除する。それまでは凍結（修正は壊れたときだけ） | 画面が1つに収まる。依存が減る | Web 画面に生成の画面を追加する手間。削除する PR で ADR-0003 を Superseded にする |
| C. すぐ凍結 | 今のまま残し、以後は修正しない。削除するかは決めない | 手間が最も少ない | 古い画面が残り続ける |

- 案 B を採用した。`app/gui/` は凍結し、修正は壊れたときだけ
- 削除する PR の前に「Web 画面で、今の PySide6 の画面で
  できることがすべてできる」ことを確認するテストを追加する
- 追記（2026-10-20）：Web 画面（Phase 3b）は予約または緊急の患者からの
  撮影を持つが、Job YAML や `quick` に相当する自由な生成の機能は持たない。
  案 B の削除の条件はまだ満たされておらず、`app/gui/` は凍結のまま残す。
  削除するかどうかは別の判断（別の PR）

## 影響

### 良い点

- 本物のモダリティを使わずに、Scheduled Workflow の流れを繰り返し
  実行できる
- 予約の値の転記と文字コードの扱いを、意図的に崩した形も含めてテストできる
- PACS の画面と見た目がそろう

### 悪い点

- 依存が増える（`fastapi`・`uvicorn`・`jinja2`・`python-multipart`・
  テスト用の `httpx`）。2026-10-18 に承認された。requirements.txt へは
  Phase 3b の PR で追加する
- ADR-0003 と spec/05_gui.md は、モダリティの画面には適用されなくなる。
  二つの画面の仕様が並ぶ間は、どちらの仕様かを冒頭で示す
- 通信のテストは、テストの中でスタブの SCP をローカルに起動するので、テストの
  時間が少し延びる

### リスク

- pydicom の版によって、ISO 2022 IR 13 と IR 87 の組の書き出しの動きが
  違いうる
  - **軽減策**：Phase 3a で4つの文字コードの書き出しと読み込みをテストする
- Orthanc の Worklists プラグインで、JIS を指定して作成した予約の
  漢字・かなが黙って消える（2026-10-18 の実測。spec/12 の 14.1）
  - **軽減策**：予約は UTF-8 で作成すると文書に書く。漢字・かなが空の予約に
    印を表示する

## 変更対象

- `spec/12_modality_emulator.md`（新規。2026-10-20 に `12a_web_screens_and_cli.md`・
  `12b_decisions_and_limits.md` と 3 本に分けた）
- `spec/05_gui.md`（冒頭に、モダリティの画面は spec/12a という注）
- `WORKFLOW.md`（実装の順の表に Phase 3a〜3c）
- `README.md`（主な特徴に1行）
- Phase 3a の PR で：`spec/04_cli.md`・`spec/08_error_handling.md`・
  `WORKFLOW.md` の層の図

## 関連する決定

- [ADR-0001: Core Library First](0001-core-library-first.md)
- [ADR-0003: PySide6 GUI](0003-pyside6-gui.md)（モダリティの画面について
  置き換える）
- [ADR-0008: PatientAge を birth_date / study_date から算出する](0008-patient-age-derived-from-dates.md)
- [ADR-0010: Storage SCP の運用仕様](0010-storage-scp-operational-decisions.md)
  （[ADR-0013](0013-remove-storage-scp.md) で Superseded）

## 参考資料

- [spec/12_modality_emulator.md](../spec/12_modality_emulator.md)
  （出典の一覧は 15 章）
- IHE Radiology TF-2 Rev. 23.0 4.5（RAD-5）・4.8（RAD-8）、
  TF-2x Appendix A
- DICOM PS3.4 K.6.1、PS3.17 DD.1
- Orthanc Book「DICOM storage commitment」、Orthanc の DICOM
  Conformance Summary
- PACS の画面の見た目の基準
