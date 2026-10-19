# ADR-0011: モダリティのダミーにする（SCU・ウェブの画面）

## ステータス

**Accepted** - 2026-10-18（承認者が spec/12 と同時に受け入れた。決まったことは
spec/12b の 18 章）

## 背景

この道具は DICOM のファイルを作るところまでで、作った画像を PACS へ
入れるには別の道具が要る。PACS・RIS の試験では、次の流れを
繰り返し流したい。

```text
ワークリストを引く → 予約を選ぶ → 予約の値で撮る → PACS へ送る → 確かめる
```

本物のモダリティを使わずにこれを流すには、この道具が「モダリティの
役」を持つ必要がある。画面が無いと、ダミーのモダリティとして
機能が足りない（技師の操作の流れを再現できない）。

### 要求

- ワークリスト（C-FIND MWL）の SCU、C-STORE・C-ECHO の SCU
- 保管の確認（Storage Commitment）・MPPS は選べる形
- 予約の値を画像に正しく写す（IHE Scheduled Workflow）
- 画面：ワークリスト・撮影・PACS・設定。tsunagi-dicom と統一感のある形
- 同じ操作を CLI でも行え、自動の試験から使える
- 実の PACS につながずに試験できる

## 決定

1. **この道具をモダリティのダミーに育てる。** 仕様は
   [spec/12_modality_emulator.md](../spec/12_modality_emulator.md)
2. **SCU の通信と手順を `app/modality/` に分け、Service Layer の
   一部として扱う。** 予約から生成の設定への写し方は Pure な処理として
   `app/core/` に置く
3. **保管の確認と MPPS は、送り先・相手ごとに選べる形にし、既定は
   使わない。**
4. **モダリティの画面はウェブの画面にする（Python の側で描く。
   FastAPI・Jinja2・HTMX・Tailwind CSS）。** モダリティの画面について、
   ADR-0003（PySide6）を置き換える。見た目の値（色・文字・部品の形）は
   tsunagi-dicom と同じにし、明るい地を既定・暗い地に切り替えられる
   形にする。画面はすっきりさせ、機能を足すより削る（2026-10-18 に
   承認者が足した方向。試験のスタブなので機能は少なくてよい。
   spec/12a の 10 章の冒頭）
5. **画面の待ち受けは既定で手元（127.0.0.1）だけ。** 手元の外で待ち
   受けるときは簡単な認証（HTTP Basic）を必須にする

### 理由

#### 1. モダリティのダミーにする理由

- 試験で要るのは「ファイル」より「装置としての振る舞い」
  （予約を引く・値を写す・送る・確かめる）
- 予約の値の写し方（Study Instance UID・受付番号・Request Attributes
  Sequence など）は、PACS・RIS の連携の不具合が出やすい所で、
  ここを正しく・わざと崩して流せることに試験の価値がある
- 既存の生成の処理（テンプレート・異常のデータ・ピクセル）を
  そのまま使える

#### 2. `app/modality/` に分ける理由

- `app/services/` は生成の処理（ファイルを作る）、`app/modality/` は
  通信と手順（相手とやり取りする）で、壊れ方と試験の道具が違う
  （通信の試験は、試験の中で偽の相手の SCP を手元に立てる）
- CLI と ウェブの画面の両方から同じ手順を使う。UI に手順を書くと
  2か所に分かれる
- 当時は `app/scp/`（受ける側）と互いに import しない形にして、並べて
  「撮る→送る→受ける」の閉じた試験にできるとした。2026-10-20 に受ける側を
  外した（[ADR-0013](0013-remove-storage-scp.md)）。試験の受け手は、試験の中の
  偽の相手（`tests/modality_peers.py`）
- 写し方を `app/core/` に置くと、通信なしで単体の試験ができる
  （ADR-0001 の Core-First と同じ考え）

#### 3. MPPS と保管の確認を選べる形にする理由

- Orthanc は MPPS（N-CREATE・N-SET）を受けない。DICOM Conformance
  Summary に無く、ソース（`CommandDispatcher.cpp`）も扱わない
  DIMSE として断る。MPPS を必須にすると、主な試験の相手で流れが
  止まる
- 保管の確認は Orthanc 1.6.0 から受けるが、相手に要求元の
  モダリティの登録が要り、結果は別の Association で非同期に来る。
  使わない試験も多い
- 実の装置でも、どちらも設定で切ることが多い

#### 4. 画面をウェブにする理由（PySide6 にしない理由）

- tsunagi-dicom（同じ作者のウェブの画面）と統一感のある形にする
  要望がある。同じ色・文字・部品の形を、Tailwind CSS の同じ値で作れる
- ブラウザがあればどの OS でも開け、PySide6（大きな包み）を入れずに
  済む。試験の機材の上で動かし、手元の PC のブラウザから見る
  使い方にも合う
- FastAPI の TestClient で、画面の応答を pytest のまま試験できる
- Python の側で描くので、core・services をそのまま呼べる。Node の
  作りは要らない（Tailwind CSS の standalone の実行ファイルで CSS を
  作り、作った CSS を commit する）

#### (b) Next.js＋Python の API を選ばない理由

- 型と試験を2つの言語で持つことになり、保守の手間と CI の仕事が増える
- Node の依存が数百の包みになる
- 統一感は見た目の値をそろえれば得られる。React の部品そのものを
  共有する必要は今は無い
- 将来、色・文字の値（design tokens）を1か所に持てば、両方から同じ値を
  使える（spec/12a の 10.1）

#### 5. 既定で手元だけにする理由

- 試験の道具で、患者の値は合成でも、網に出すと誰でも撮影・送信を
  起こせる
- 利用者の管理や監査の記録は、この道具の目的ではない
  （tsunagi-dicom とは目的が違う）。手元の外に出すときだけ最小の
  認証を求め、パスワードが無ければ起動しない（安全を既定にする）

## 既存の PySide6 の GUI の扱い（案 B に決まった。2026-10-18）

| 案 | 中身 | 良い点 | 悪い点 |
|----|------|--------|--------|
| A. 残す | 生成の道具の画面として残し、保守を続ける。Phase 2b（GUI のフル機能）は進めない | 今の利用者の使い方が変わらない | 画面が2種類になり、同じ機能を2回作る誘因になる |
| **B. 後で外す（採った）** | Phase 3b でウェブの画面が生成の機能（いまの PySide6 の画面と同じ範囲）も持てたら、別の PR で `app/gui/`・PySide6・pytest-qt を外す。それまでは凍結（直すのは壊れたときだけ） | 画面が1つに収まる。依存が減る | ウェブの画面に生成の画面を足す手間。外す PR で ADR-0003 を Superseded にする |
| C. すぐ凍結 | 今のまま残し、以後は直さない。外すかは決めない | 手間が最も少ない | 古い画面が残り続ける |

- 承認者は案 B を採った。`app/gui/` は凍結し、直すのは壊れたときだけ
- 外す PR の前に「ウェブの画面で、いまの PySide6 の画面で
  できることがすべてできる」ことを確かめる試験を足す
- 追記（2026-10-20）：ウェブの画面（Phase 3b）は予約または緊急の患者からの
  撮影を持つが、Job YAML や `quick` に当たる自由な生成の入口は持たない。
  案 B の外す条件はまだ満たされておらず、`app/gui/` は凍結のまま残す。
  外すかどうかは別の判断（別の PR）

## 影響

### 良い点

- 本物のモダリティを使わずに、Scheduled Workflow の流れを繰り返し
  流せる
- 予約の値の写し方と文字コードの扱いを、わざと崩した形も含めて試せる
- tsunagi-dicom と見た目がそろう

### 悪い点

- 依存が増える（`fastapi`・`uvicorn`・`jinja2`・`python-multipart`・
  試験用の `httpx`）。2026-10-18 に承認された。requirements.txt へは
  Phase 3b の PR で足す
- ADR-0003 と spec/05_gui.md は、モダリティの画面には効かなくなる。
  二つの画面の仕様が並ぶ間は、どちらの仕様かを冒頭で示す
- 通信の試験は、試験の中で偽の相手の SCP を手元に立てるので、試験の時間が
  少し延びる

### リスク

- pydicom の版によって、ISO 2022 IR 13 と IR 87 の組の書き出しの動きが
  違いうる
  - **軽減策**：Phase 3a で4つの文字コードの書き出しと読み戻しを試験する
- Orthanc の Worklists のプラグインで、JIS を指定して作った予約の
  漢字・かなが黙って消える（2026-10-18 の実測。spec/12b の 16.1）
  - **軽減策**：予約は UTF-8 で作ると文書に書く。漢字・かなが空の予約に
    印を出す

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
  （出典の一覧は [spec/12b](../spec/12b_decisions_and_limits.md) の 19 章）
- IHE Radiology TF-2 Rev. 23.0 4.5（RAD-5）・4.8（RAD-8）、
  TF-2x Appendix A
- DICOM PS3.4 K.6.1、PS3.17 DD.1
- Orthanc Book「DICOM storage commitment」、Orthanc の DICOM
  Conformance Summary
- tsunagi-dicom `docs/spec.md` 2（見た目の基準）
