# ADR-0028: 画面の CSS は 3 製品で共通の ui-kit の写しを読み、DTG の CSS には差分だけを書く

- 状態：採用
- 作成日：2026-10-26
- 最終更新日：2026-10-29

## 背景

DTG・ris-emulator・tsunagi-dicom の 3 製品は、同じ画面の決まり（外枠・左のナビ・
検索の帯・一覧の表・状態の札・知らせ・区画）で組んでいる。ところが DTG は Tailwind の
`input.css` の中に、ris-emulator は手書きの `app.css` の中に、同じ部品をそれぞれ
別の名前で持っていた（左のナビの `.nav-group`・`.nav-item` と `.nav-g`・`.nav-i`、
区画の中身の `.sec-body` と `.sec > .in` など）。`.st`・`.sum`・`.searchband` は同じ
定義の写しが 2 つあり、片方だけを直すと、3 製品の見た目が少しずつずれていった。

3 製品は公開のリポジトリで、CI はネットワークの外の物を読まずに動かしたい。

## 決定

1. 色・文字・間の値（`tokens.css`）と部品の CSS（`components.css`）は、3 製品で共通の
   ui-kit の写しを `app/web/static/ui-kit/` に置いて読む。版は同じ場所の `VERSION` に
   書く。取り込みの仕組み（サブモジュール・パッケージ）は作らない。写しなら CI が
   外を読まずに済む
2. 写しは DTG の側で直さない。直したいときは ui-kit の側を直し、版が上がったら、
   同じ版の写しに替える PR を出す。3 製品の見た目がずれないようにするため
3. `base.html` は tokens.css → components.css → app.css の順に読む。DTG の CSS
   （`app.css`、元は `input.css`）は後に読むので、同じ強さの規則なら ui-kit に勝つ
4. `input.css` には値を書かない。テンプレートの Tailwind の色の名前（`bg-surface`・
   `text-label` など）は、`@theme inline` で tokens.css の変数へつなぐだけにする。
   tokens.css の `--color-*` はすべてつなぐ
5. `input.css` に書く部品は、ui-kit に無い DTG だけの物（撮影のルーチンの表・UID の
   コピー・撮影の途中の表示など）だけにする。ui-kit と同じ名前の
   定義は置かない
6. テンプレートのクラスの名前は ui-kit の名前にする（`.nav-g`・`.nav-i`・`.sec > h2`・
   `.sec > .in`・`.field > .l`・`.tbl`・`.listhead`・`.kv`・`.notice[data-k]` など）
7. ui-kit は CSS の層（`@layer`）の外にあり、Tailwind の層の中の utility より強い。
   テンプレートに書いた utility（`mt-2` など）が ui-kit の初期化に負けないよう、
   Tailwind の utility は `important` で作る

## 検討した選択肢

- **ui-kit を Tailwind の `@import` で `input.css` に取り込む。** 1 つの CSS に
  なるが、写しを Tailwind が書き換えた物が届き、ris-emulator（Tailwind を使わない）と
  同じ写しを読んでいるかを確かめにくい。採用しない
- **ui-kit を Tailwind の `@layer components` の中に置く。** utility が勝つ順に
  なるが、写しを直すことになる（決定 2 に反する）。採用しない
- **DTG の部品の名前のまま、値だけを合わせる。** 名前が 3 製品で違うままで、同じ
  部品の写しが残る。採用しない

## 結果

- 3 製品の部品の見た目と名前が 1 つになり、直す場所が ui-kit の 1 か所になる
- 値と 10.2 の表の一致は、`tests/web/test_theme_tokens.py` が tokens.css を読んで
  確かめる。`input.css` が tokens.css の色をすべてつなぎ、値を書いていないことも
  確かめる
- ui-kit の版が上がるたびに、写しを替える PR が要る
- Tailwind の utility が `!important` になる。ui-kit の状態の規則（hover など）と
  同じ性質を utility で書くと、utility が勝つ。テンプレートでは部品の性質を utility で
  上書きしない

## 関連

- [spec/12a](../spec/12a_web_screens_and_cli.md) の 10.1・10.2
- [ADR-0011](0011-modality-emulator.md)（Web 画面の技術）
