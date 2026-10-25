"""接続の状態：最後に試した結果を覚える（docs/spec/12a の 10.3）.

上の帯の「接続の状態」に出す全体の状態の札と、押したときの中身のもとにする。DTG は常に接続を
張っているわけではないので、ワークリストの検索と、送信先の接続確認の最後の結果だけを持つ
（画面を動かしている間だけ。保存しない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

KIND_OK = "ok"
KIND_NG = "ng"
KIND_UNKNOWN = "plan"
LABEL_OK = "接続中"
LABEL_NG = "一部が接続不可"
LABEL_UNKNOWN = "未確認"


@dataclass(frozen=True)
class Probe:
    """1 つの相手に最後に試した結果."""

    ok: bool
    at: str

    @property
    def kind(self) -> str:
        return KIND_OK if self.ok else KIND_NG


@dataclass
class LinkStatus:
    worklist: Probe | None = None
    destinations: dict[str, Probe] = field(default_factory=dict)

    def record_worklist(self, ok: bool) -> None:
        self.worklist = Probe(ok, _now())

    def record_destination(self, name: str, ok: bool) -> None:
        self.destinations[name] = Probe(ok, _now())

    def overall(self, destination_names: list[str]) -> tuple[str, str]:
        """全体の状態の札の（種類, 文字）。失敗が 1 つでもあれば「一部が接続不可」.

        数えるのは、いま設定にある送信先の結果だけ。
        """
        probes = [self.worklist, *(self.destinations.get(name) for name in destination_names)]
        probes = [probe for probe in probes if probe]
        if not probes:
            return KIND_UNKNOWN, LABEL_UNKNOWN
        if any(not probe.ok for probe in probes):
            return KIND_NG, LABEL_NG
        return KIND_OK, LABEL_OK


def _now() -> str:
    return datetime.now().strftime("%m/%d %H:%M")
