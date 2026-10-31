"""患者の性別の値（M・F・O・U。医療システム共通の決め）.

画面と製品の中の値は M・F・O・U の 4 つで、わからない・言えないは U。DICOM の
Patient's Sex（0010,0040）の列挙値は M・F・O だけなので、U は DICOM に書くときに空にして
書く（Type 2 の空。規格に違反しない）。DICOM から読むときは、空と M・F・O 以外を U と読む。
"""

from __future__ import annotations

SEX_VALUES = ("M", "F", "O", "U")
SEX_UNKNOWN = "U"
_DICOM_SEX_VALUES = frozenset({"M", "F", "O"})


def to_dicom_sex(value: str) -> str:
    """DICOM に書く Patient's Sex：M・F・O はそのまま、U と空は空にする."""
    return value if value in _DICOM_SEX_VALUES else ""


def from_dicom_sex(value: str) -> str:
    """DICOM から読んだ Patient's Sex：空と M・F・O 以外は U と読む."""
    return value if value in _DICOM_SEX_VALUES else SEX_UNKNOWN
