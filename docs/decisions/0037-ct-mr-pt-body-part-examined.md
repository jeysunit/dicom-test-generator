# ADR-0037: CT・MR・PT の画像にも Body Part Examined を入れ、検査の部位ごとに値を決める

- 状態：採用
- 作成日：2026-11-01
- 最終更新日：2026-11-01

## 背景

CT の画像に Body Part Examined (0018,0015) が無く、dicom3tools の dciodvfy が
General Series の Laterality (0020,0060)（Type 2C）の欠落を Error にした。MR・PT でも同じだった。

規格では、Laterality は「検査した部位が対になる構造で、Image Laterality などが無いとき」に必須
（PS3.3 C.7.3.1）。Body Part Examined は Type 3 で、無ければ対になる部位かどうかを決められず、
dciodvfy は欠落を Error にする。対になるかどうかは PS3.16 Annex L の Table L-5 で決まる
（胸部・腹部・頭部・心臓・脊椎は N、膝・手・肩は Y）。

DTG は CR・DX だけ、ルーチンの `body_part` と `laterality` を持っていた（[ADR-0034](0034-cr-dx-images.md)）。

## 決定

1. **CT・MR・PT のシリーズの General Series に Body Part Examined を入れる。** 値は PS3.16
   Annex L の Table L-1 の定義語で、ルーチンの `body_part` が決める。線量の報告（SR）は
   General Series の Laterality も Body Part Examined も持たないので書かない
2. **ルーチンの `body_part` は CT・MR・PT で任意、書かなければ `CHEST`（`DEFAULT_BODY_PART`）。**
   ルーチンを使わず手で入れたシリーズも `CHEST`。CR・DX の手で入れたシリーズと同じ値にそろえる。
   同梱のルーチンは全部 `body_part` を書く（試験が見る）
3. **対になる部位（膝・手・肩）は `laterality`（`R`・`L`）を General Series の Laterality に書く。**
   同梱の MR 膝・MR 肩は、CR・DX の膝・手と同じ架空の `R`
4. **部位の値は spec/06 の 5.6 の表で決める。** CR・DX が書ける部位は従来の 6 つのまま
5. 部位の語を足すのは、Table L-1 の語に限る。US のルーチンは画像をまだ作らないので書かない

## 検討した選択肢

- **`body_part` を CT・MR・PT のルーチンで必須にする（採用しない）。** 利用者が作ったルーチンが
  読めなくなる。同梱のルーチンは試験で全部書かせるので、既定の部位が黙って入るのは
  利用者のルーチンだけ
- **既定の部位を `PHANTOM`（Table L-1 の定義語。対にならない）にする。** 合成のデータである
  ことは正直に出せるが、ビューアや PACS の部位の絞り込みで人の検査として扱われにくい。
  CR・DX の既定が `CHEST` なので、そろえて採用しない
- **Laterality だけを足す（Body Part Examined は入れない）。** Laterality は対になる部位だけ
  に書く値で、部位が分からないまま書くと規格に反する。採用しない
- **肝臓ダイナミックを `LIVER` にする。** Table L-1 に語はあるが、CID 4031 に無く、撮影の範囲も
  腹部全体なので `ABDOMEN` にする

## 結果

- CT・MR・PT の全画像に Body Part Examined が入り、dciodvfy の Laterality の Error が消える
- MR 膝・MR 肩の画像には Laterality `R` が入る
- 手で入れた CT・MR・PT のシリーズには `CHEST` が入る
- 既存のジョブの YAML・ルーチンは、書き換えずに動く

## 関連

- [spec/06](../spec/06_dicom_rules.md) の 5.6
- [spec/03](../spec/03_data_models.md) の 3.2
- [ADR-0034](0034-cr-dx-images.md)：CR・DX の部位と左右
- 出典：PS3.3 C.7.3.1（General Series Module）、PS3.16 Annex L
  （Table L-1・Table L-5）、CID 4031
