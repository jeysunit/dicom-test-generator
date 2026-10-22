"""Pydantic の検証の誤りを、値を出さずに文にする（docs/spec/12_modality_emulator.md 12 章）.

`str(ValidationError)` は `input_value=...` で入っていた値を出す。壊れた保存のデータでは
そこに患者の氏名が入りうるので、画面・CLI・ログには「項目の名前: 原因」だけを出す。
"""

from __future__ import annotations

from pydantic import ValidationError

MAX_LISTED_ERRORS = 5


def describe_validation_error(exc: ValidationError) -> str:
    """`items.0.key: Field required; ...` の形（値は出さない）."""
    errors = exc.errors(include_input=False, include_url=False, include_context=False)
    parts = [
        f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
        for error in errors[:MAX_LISTED_ERRORS]
    ]
    if len(errors) > MAX_LISTED_ERRORS:
        parts.append(f"... ({len(errors) - MAX_LISTED_ERRORS} more)")
    return "; ".join(parts)
