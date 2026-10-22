# Design

## Context

再現の条件：ワークリストを取得し、行を選ばずに「取得し直す」を押す。

- `app/web/templates/_worklist_results.html:57` の「取得し直す」は `type="button"` で、
  `hx-include="#pick"` によりフォームの値を送る。ラジオボタン（`name="key"`）が
  選ばれていなければ `key` は送られない。ラジオボタンの `required` は、submit の
  ボタンにしか効かない
- `app/web/routes/worklist.py:98` の `worklist_refresh` は `key: FormStr = ""` で
  受けるので、空文字のまま `ModalityService.refresh_item("")` を呼ぶ
- `app/modality/service.py:410` の `find_item` は空の鍵を見つけられず、
  `ModalityError("Worklist item not found in the last query: ", {"worklist_key": "",
  "hint": "run 'worklist query' first"})` を投げる。画面は `str(exc)` をそのまま
  表示する（`app/web/rendering.py` の `error_text`）

行を選んでから押せば今も動く（`tests/web/test_pages.py` の
`test_worklist_detail_and_refresh` は行を選んだ要求だけを試している）。

## Goals / Non-Goals

**Goals:**

- 行を選ばずに押せないようにし、押せたとしても問い合わせずに日本語で知らせる
- 取得し直す・撮影の画面を開くときの失敗を、利用者向けの日本語にする

**Non-Goals:**

- 「取得し直す」を、最後の条件で一覧全体を取得し直すボタンに変えること
  （一覧全体は「ワークリストを取得」で取得し直せる。spec 12a 10.4 の決定を変えない）
- CLI の文言・終了コードの変更
- ほかの画面の英語のエラー（送信・C-ECHO など）を日本語にすること

## Decisions

1. **ボタンは、行を選ぶまで `disabled` にする。** `app.js` で、`#pick` の
   `name="key"` が選ばれたら押せるようにする（CSP がインラインのスクリプトを禁じて
   いるので、`app.js` に書く）。取得し直した後の一覧は選んだ行に印を付けて返す
   ので、ボタンは押せる状態で描く。スクリプトが無効でもサーバーの確認で止まる。
   採用しなかった案：ラジオボタンの1行目を最初から選んでおく（意図しない予約を
   取得し直す）
2. **失敗の種類を例外で区別し、日本語の文言は Web の層で決める。**
   `ModalityError` の子として「最後の一覧に無い」「ワークリストにもう無い」を作り、
   時間切れは今の `WorklistQueryError`（`partial`）を使う。CLI は今の英語の文言と
   終了コードのまま。採用しなかった案：サービスの文言を日本語にする（CLI の文言と
   ログが変わり、spec 08 の文言の方針と食い違う）
3. **知らせに出す値は、受付番号と秒数だけにする。** 受付番号は相手から来る値なので
   自動エスケープのまま表示する（spec 12a 10.8）

## Risks / Trade-offs

- [ボタンを `disabled` にしたまま、選んだ行が残る描き方がある] → 一覧を描くときに
  選んだ行があれば押せる状態で描く。テストで両方を確かめる
