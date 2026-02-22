# ADR-0007: Patient Size（身長）の単位を cm に変更

## Status

**Accepted** - 2026-02-22

## Context

仕様書（spec/03_data_models.md, spec/07_job_schema.md）では、
Patient の `size` フィールドを **メートル（m）** で定義していた:

```python
size: float | None = Field(None, ge=0, le=3, description="身長（m）")
```

Job YAML の例:

```yaml
size: 1.70  # メートル
```

しかし、以下の問題が発生した:

1. **外部データとの不整合**: 患者マスタデータ（`data/patients_master.yaml`）では身長が cm 単位（例: `172.0`）で記録されている。これは医療現場や外部システムでの一般的な表記に合致している。
2. **ユーザー直感との不一致**: 日本の医療現場では身長を cm で記録するのが標準。m 表記はユーザーにとって直感的でない。
3. **DICOM 規格との関係**: DICOM タグ (0010,1020) Patient's Size は m 単位だが、これは内部変換で対応可能。

### 選択肢

1. **入力を m のまま維持**: 仕様通りだが外部データとの変換が必要
2. **入力を cm に変更**: 外部データ・ユーザー直感と一致。DICOM 出力時に m に変換

## Decision

**Patient.size の単位を cm に変更する。DICOM タグ設定時にプログラム内で m に変換する。**

### 変更箇所

- `spec/03_data_models.md`: `le=3` → `le=300`、description を「身長（cm）」に変更
- `spec/07_job_schema.md`: 例の値を `1.70` → `170.0`、説明を「身長（cm）」に変更
- `app/core/models.py`: `Patient.size` の制約を `le=300` に変更、`size_in_meters` プロパティで変換
- `app/core/generator.py`: `ds.PatientSize` に `size_in_meters` を使用

### 変換ロジック

```python
class Patient(BaseModel):
    size: float | None = Field(None, ge=0, le=300, description="身長（cm）")

    @property
    def size_in_meters(self) -> float | None:
        """DICOM Patient's Size (0010,1020) 用にメートル単位で返す."""
        if self.size is None:
            return None
        return self.size / 100.0
```

## Consequences

### Positive

- 外部患者マスタデータ（cm 表記）をそのまま読み込み可能
- 医療現場の慣習と一致し、ユーザーが直感的に入力可能
- DICOM 規格準拠は `size_in_meters` プロパティで保証

### Negative

- 仕様書の既存例・ドキュメントの変更が必要
- DICOM 出力値と入力値の単位が異なるため、変換忘れに注意が必要
  - **軽減策**: `size_in_meters` プロパティを唯一の変換経路として明示

## Related Decisions

- [spec/03_data_models.md](../spec/03_data_models.md)
- [spec/07_job_schema.md](../spec/07_job_schema.md)
