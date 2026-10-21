"""氏名の欄の空白を ^ に置き換える（docs/spec/12a の 10.5）."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.core.person_name import compose_person_name, normalize_name_group


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Yamada Taro", "Yamada^Taro"),
        ("山田　太郎", "山田^太郎"),
        ("  Yamada   Taro  ", "Yamada^Taro"),
        ("やまだ\u3000 \u3000たろう", "やまだ^たろう"),
        ("Yamada^Taro", "Yamada^Taro"),
        ("Yamada ^ Taro", "Yamada^Taro"),
        ("YAMADA", "YAMADA"),
        ("", ""),
        ("　 ", ""),
    ],
)
def test_normalize_name_group(value, expected) -> None:
    assert normalize_name_group(value) == expected


@pytest.mark.parametrize("value", ["Yamada=Taro", "A\x1bB", "A\u202eB", "A\nB", "A\tB"])
def test_group_separator_and_control_characters_are_refused(value) -> None:
    with pytest.raises(ValidationError):
        normalize_name_group(value)


def test_compose_person_name() -> None:
    assert compose_person_name("Yamada Taro", "山田　太郎", "やまだ たろう") == (
        "Yamada^Taro=山田^太郎=やまだ^たろう"
    )
    assert compose_person_name("Kinkyu Taro", "", "") == "Kinkyu^Taro"
    assert compose_person_name("Kinkyu", "", "きんきゅう") == "Kinkyu==きんきゅう"
