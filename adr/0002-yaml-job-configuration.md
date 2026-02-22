# ADR-0002: YAML Job Configuration

## ステータス

**Accepted** - 2025-02-21

## 背景

DICOM生成の設定を管理する方法を決定する必要がある。

### 選択肢

1. **JSON形式**: 構造化データ、厳密な文法
2. **YAML形式**: 人間が読みやすい、コメント可
3. **TOML形式**: シンプル、Pythonでは標準
4. **Python dict**: コードで直接記述

### 要求

- 人間が手で編集可能
- バージョン管理（Git）に適している
- CLIからもGUIからも使える
- テストケースとして保存可能

## 決定

YAML形式をJob設定のフォーマットとして採用する。

### 理由

#### YAML の利点

1. **可読性が高い**
   - インデントベース、Pythonに似た構文
   - コメントが書ける（JSON不可）
   - 長いUID等も改行で見やすく

2. **Git管理に最適**
   - テキストファイル
   - diff が見やすい
   - マージコンフリクトが解決しやすい

3. **Python標準ライブラリに近い**
   - PyYAMLで簡単に読み書き
   - Pydanticと組み合わせやすい

4. **業界標準**
   - Kubernetes、Docker Compose等で広く使用
   - CI/CDパイプラインに統合しやすい

#### JSON を選ばない理由

- コメントが書けない
- 人間が編集しにくい（カンマ、ブラケット）
- UID等の長い文字列が見づらい

#### TOML を選ばない理由

- ネストが深い構造には不向き
- シリーズリスト等の配列表現が冗長

#### Python dict を選ばない理由

- 非プログラマーが編集できない
- バージョン管理しにくい

## 影響

### 良い点

- ✅ テストケースをYAMLで保存できる
- ✅ Gitで変更履歴を追跡できる
- ✅ 生成AIがJob YAMLを生成しやすい
- ✅ CI/CDパイプラインに統合しやすい
- ✅ CLIとGUIで同じフォーマットを共有

### 悪い点

- ⚠️ YAMLパースエラーが発生しうる
  - **軽減策**: Pydanticで厳密な検証
- ⚠️ インデントミスが起きやすい
  - **軽減策**: エディタのYAMLサポート、バリデーションコマンド提供

### 中立

- YAML 1.1 vs 1.2の違いに注意
  - PyYAMLはYAML 1.1（`yes/no`がboolになる等）
  - 本アプリでは問題なし

## 実装

- Job設定は `.yaml` 拡張子
- PyYAML 6.0.1以上を使用
- Pydantic v2でスキーマ検証

### 例

```yaml
# job.yaml - DICOM生成設定
job_name: "CT検査テストデータ"
output_dir: "output/test"

patient:
  patient_id: "P000001"
  patient_name:
    alphabetic: "YAMADA^TARO"
    ideographic: "山田^太郎"
  birth_date: "19800115"
  sex: "M"

study:
  accession_number: "ACC000001"
  study_date: "20240115"
  study_time: "143000"
  num_series: 3

series_list:
  - series_number: 1
    num_images: 10
  - series_number: 2
    num_images: 20
  - series_number: 3
    num_images: 20

modality_template: "fujifilm_scenaria_view_ct"
pixel_spec:
  mode: "ct_realistic"
# ...
```

## 関連する決定

- [ADR-0001: Core Library First](0001-core-library-first.md)

## 参考資料

- [07_job_schema.md](../spec/07_job_schema.md)
- PyYAML: <https://pyyaml.org/>
- YAML Spec: <https://yaml.org/spec/1.2.2/>
