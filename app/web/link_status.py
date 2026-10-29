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
# 接続確認の結果を読み上げる 3 つ目の型。状態を読めない・通信の失敗のとき（_band.html が app.js に渡す）
CHECK_UNREADABLE = "接続を確かめられませんでした。"

# 接続確認の失敗の理由の 1 句と、次にすること（10.6）。英語の原文は画面に出さず、記録に残す。
# pynetdicom は、接続の拒否・時間切れ・ホスト名を引けないことを区別せずに返す
REASON_NO_ANSWER = "応答がありません"
REASON_REFUSED = "接続を断られました"
REASON_PEER_FAILED = "相手が失敗を返しました"
REASON_AE_TITLE = "AEタイトルが合いません"
_ECHO_REASONS = (
    ("AEタイトル", REASON_AE_TITLE, "相手の側に、この装置の AEタイトルを登録してください。"),
    ("rejected by the peer", REASON_REFUSED, "相手の側の AEタイトルの登録と設定を確かめてください。"),
    ("failed with status", REASON_PEER_FAILED, "相手の側の記録を確かめてください。"),
)
_NEXT_NO_ANSWER = "相手が動いているかと、ホスト名とポート番号を確かめてください。"


def echo_reason(message: str) -> tuple[str, str]:
    """接続確認の失敗の原文を、（理由の 1 句, 次にすること）にする."""
    for needle, reason, next_step in _ECHO_REASONS:
        if needle in message:
            return reason, next_step
    return REASON_NO_ANSWER, _NEXT_NO_ANSWER


@dataclass(frozen=True)
class Probe:
    """1 つの相手に最後に試した結果。失敗のときは理由の 1 句を持つ."""

    ok: bool
    at: str
    reason: str = ""

    @property
    def kind(self) -> str:
        return KIND_OK if self.ok else KIND_NG


@dataclass
class LinkStatus:
    worklist: Probe | None = None
    destinations: dict[str, Probe] = field(default_factory=dict)

    def record_worklist(self, ok: bool, reason: str = "") -> None:
        self.worklist = Probe(ok, _now(), reason)

    def record_destination(self, name: str, ok: bool, reason: str = "") -> None:
        self.destinations[name] = Probe(ok, _now(), reason)

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


def check_summary(results: list[bool]) -> str:
    """手で押した「接続確認」の結果を読み上げる 1 文（部品集の 3 つの型の、確かめられた場合の 2 つ）.

    N は確かめた件数、M は失敗の件数。DTG は状態を持たない相手を持たないので、全部を数える。
    """
    total = len(results)
    failed = results.count(False)
    if failed:
        return f"{total} 件のうち {failed} 件に接続できませんでした。"
    return f"{total} 件すべてに接続できました。"


def _now() -> str:
    # 日時は yyyy/MM/dd HH:mm（部品集の「日付と時刻」）
    return datetime.now().strftime("%Y/%m/%d %H:%M")
