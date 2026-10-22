# Design

## Context

今の DTG は、自分の AE タイトルを `ModalityConfig.ae_title` の1つだけ持ち、
`ModalityService` がそれを各 SCU（`worklist_scu`・`store_scu`・`mpps_scu`・
`commitment_scu`）に渡している。`station_name` は MPPS の Performed Station Name に
だけ使い、画像の Station Name (0008,1010) はテンプレート・装置プロファイル・病院
テンプレートで決まる（spec 12 の 6.2）。保管確認の待ち受けは `require_called_aet` で
自分の AE タイトルあての Association だけを受ける。

## Goals / Non-Goals

**Goals:**

- 装置（表示名・AE タイトル・Station Name）を設定に複数書き、画面と CLI で選ぶ
- 選んだ装置を、通信の Calling AE Title・画像・MPPS に一貫して使う
- 切り替えの前に作った送信・MPPS・保管確認が、切り替えの後も同じ AE タイトルで
  続くようにする

**Non-Goals:**

- 装置ごとのモダリティ・テンプレート・送信先の切り替え（テンプレートと装置
  プロファイルの選択は今のまま撮影の画面で行う）
- 画面で装置を追加・編集すること（設定の画面は読み取り専用のまま。spec 12a 10.7）
- 装置ごとに別の待ち受けのポートを持つこと

## Decisions

1. **設定の形。** `modality.stations:` に `name`（表示名）・`ae_title`・
   `station_name`（空でよい）を並べ、`modality.default_station` で既定を選ぶ。
   `stations` が無ければ、今の `ae_title`・`station_name` から装置1つの一覧を作る。
   両方を書いたら設定の誤りにする（どちらが効くかを迷わせない）
2. **選んだ装置の記録。** 状態の保存先（`state_dir`）のファイルに表示名を1つ
   記録する。画面と CLI が同じ記録を読む（実機のモダリティの「この装置」に近い）。
   記録の表示名が設定に無くなっていたら、既定の装置に戻して画面に知らせる。
   採用しなかった案：画面のプロセスの中だけで覚える（再起動で戻り、CLI と画面で
   装置が食い違う）
3. **切り替えの排他。** 撮影の排他（`_exam_lock`）と送信の最中は切り替えを断る。
   撮影は開始の時点の装置を最後まで使う（撮影の途中で値が変わらないように、撮影の
   依頼に装置の値を写してから始める）
4. **Station Name の優先順。** 装置の Station Name が空でなければ、それを画像に
   入れる。空なら今の順（病院テンプレート → 装置プロファイル → テンプレート）。
   理由：Station Name は「その画像を作った機械の名前」（PS3.3 C.7.5.1）で、装置の
   切り替えが表すものと同じだから。ADR に書く
5. **行に AE タイトルを記録する。** 送信キューの `jobs` と MPPS の行に、作ったときの
   Calling AE Title の列を足す。既存の DB は列を足し、今の設定の AE タイトルで埋める。
   MPPS の行が送信先を行に固定している決まり（spec 12 の 8.4.1）と同じ考え方
6. **保管確認の待ち受け。** `require_called_aet` は1つの AE タイトルにしか効かない
   ので、待ち受けの Called AE Title の確認を、設定の装置の AE タイトルの集合で
   行う（`EVT_REQUESTED` などで確かめ、外れたら理由 7 で拒否する）。受けた結果は、
   要求を記録した行の Calling AE Title と、届いた Association の Called AE Title が
   合うときだけ採る
7. **拒否の理由。** `association_error` は、pynetdicom が返す A-ASSOCIATE-RJ の
   Result・Source・Reason を見て、理由 3 なら AE タイトルの登録を促す文言にする。
   それ以外の拒否は今の文言のまま

## Risks / Trade-offs

- [相手に登録していない装置に切り替えて撮ると、送信・MPPS が拒否される] → 拒否の
  理由を知らせる（要件）。設定の画面に、使う装置の AE タイトルを PACS・RIS に登録
  する旨を出す（今の Orthanc の `DicomModalities` の案内に装置の一覧を足す）
- [既存の DB に列を足す] → 列を足すだけで、行は消さない。移行のテストを書く
- [CLI と画面が同じ記録を読むので、CLI で切り替えると画面も変わる] → CLI には
  記録を書き換えるコマンドを作らず、`--station` はそのコマンドだけに効くようにする

## Open Questions

- 装置ごとに既定のテンプレート（CT1号機なら `ct_generic`）を結び付けるか。今回は
  入れない（撮影の画面のテンプレートの選択で足りる）
