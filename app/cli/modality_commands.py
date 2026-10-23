"""モダリティのダミーの CLI（docs/spec/12a_web_screens_and_cli.md 11 章）.

結果は標準出力、エラーは標準エラー。`--json` のときは標準出力に JSON だけを出す。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, TextIO

from app.cli.terminal import json_for_terminal, sanitize_for_terminal
from app.core.exceptions import ConfigurationError, StorageCommitmentError, StoreError
from app.core.models import ScheduledPatient, WorklistItem
from app.modality.config import load_modality_config
from app.modality.service import ExamRequest, ModalityService, SendResult
from app.modality.worklist_scu import (
    WorklistQuery,
    WorklistQueryResult,
    parse_date_option,
)

ANY = "any"
DEFAULT_IMAGES_PER_SERIES = 1
DEFAULT_CONFIG = "config/app_config.yaml"
CHARSET_CHOICES = ("auto", "utf8", "jis", "jis_kana")
PIXEL_MODE_CHOICES = ("simple_text", "ct_realistic")
ABNORMAL_LEVEL_CHOICES = ("none", "mild", "moderate", "severe")
QUEUE_STATUS_CHOICES = ("pending", "sending", "sent", "failed")
STALE_MARK = "  [STALE]"


def register_modality_commands(
    subparsers: argparse._SubParsersAction, default_log_file: str
) -> None:
    """echo・worklist・exam・send・queue・commit・mpps のサブコマンドを足す（11.1）."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", default=DEFAULT_CONFIG, help=f"設定ファイル（default: {DEFAULT_CONFIG}）"
    )
    common.add_argument("-v", "--verbose", action="store_true", help="詳細ログを表示")
    common.add_argument(
        "--log-file", default=default_log_file, help=f"ログファイル（default: {default_log_file}）"
    )
    common.add_argument("--json", action="store_true", help="結果を JSON で出す")
    common.add_argument(
        "--station",
        help="このコマンドだけ使う装置の表示名（設定の stations。無ければ画面で選んだ装置）",
    )

    echo_parser = subparsers.add_parser("echo", parents=[common], help="C-ECHO で疎通を確かめる")
    echo_target = echo_parser.add_mutually_exclusive_group()
    echo_target.add_argument("--to", help="送り先の名前（default: 既定の送り先）")
    echo_target.add_argument("--worklist", action="store_true", help="ワークリストの相手に送る")
    echo_parser.set_defaults(func=echo_command)

    worklist_parser = subparsers.add_parser("worklist", help="ワークリスト（C-FIND MWL）")
    worklist_sub = worklist_parser.add_subparsers(dest="worklist_command")
    query_parser = worklist_sub.add_parser("query", parents=[common], help="ワークリストを引く")
    query_parser.add_argument(
        "--date", default="today", help="today・YYYYMMDD・YYYYMMDD-YYYYMMDD（default: today）"
    )
    query_parser.add_argument("--modality", help="モダリティ。any で条件にしない")
    query_parser.add_argument("--station-aet", help="予定の AE タイトル。any で条件にしない")
    query_parser.add_argument("--patient-id", help="患者 ID")
    query_parser.add_argument("--patient-name", help="氏名（各成分の末尾に * を足す）")
    query_parser.add_argument("--accession", help="受付番号")
    query_parser.set_defaults(func=worklist_query_command)
    show_parser = worklist_sub.add_parser(
        "show", parents=[common], help="最後に引いた予約の1件を出す"
    )
    show_parser.add_argument("key", help="予約の鍵")
    show_parser.set_defaults(func=worklist_show_command)

    exam_parser = subparsers.add_parser(
        "exam", parents=[common], help="予約（または緊急の患者）で撮る"
    )
    source = exam_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-worklist", metavar="KEY", help="予約の鍵")
    source.add_argument("--emergency", action="store_true", help="予約なし（緊急の患者）")
    exam_parser.add_argument("--refresh", action="store_true", help="撮る前に予約を引き直す")
    exam_parser.add_argument("--patient-id", help="緊急の患者の ID")
    exam_parser.add_argument("--patient-name", help="緊急の患者の氏名（PN）")
    exam_parser.add_argument("--birth-date", help="緊急の患者の生年月日（YYYYMMDD）")
    exam_parser.add_argument("--sex", choices=("M", "F", "O"), help="緊急の患者の性別")
    exam_parser.add_argument("--study-description", help="検査の記述（--emergency のとき）")
    exam_parser.add_argument("-m", "--modality", help="モダリティテンプレート")
    exam_parser.add_argument(
        "--profile", help="装置のプロファイル（docs/spec/13。default: 設定の default_profile）"
    )
    exam_parser.add_argument("--hospital", help="病院テンプレート")
    exam_parser.add_argument("-s", "--series", type=int, default=1, help="シリーズ数")
    exam_parser.add_argument(
        "-i",
        "--images",
        help=(
            "各シリーズの画像数（カンマ区切り）。省くと、シリーズごとに"
            f"{DEFAULT_IMAGES_PER_SERIES} 画像"
        ),
    )
    exam_parser.add_argument("--pixel-mode", choices=PIXEL_MODE_CHOICES, help="ピクセル")
    exam_parser.add_argument(
        "--abnormal-level", choices=ABNORMAL_LEVEL_CHOICES, default="none", help="異常のデータ"
    )
    exam_parser.add_argument("--charset", choices=CHARSET_CHOICES, help="画像の文字コード")
    exam_parser.add_argument("-o", "--output", help="出力のフォルダ")
    exam_parser.add_argument("--send", action="store_true", help="作った後に送る")
    exam_parser.add_argument("--to", help="--send の送り先（default: 既定の送り先）")
    exam_parser.add_argument(
        "--mpps",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="この撮影だけ MPPS を送る・送らない（default: 設定の worklist.use_mpps）",
    )
    exam_parser.set_defaults(func=exam_command)

    send_parser = subparsers.add_parser(
        "send", parents=[common], help="出力のフォルダの画像を送る"
    )
    send_parser.add_argument("folder", help="画像のフォルダ")
    send_parser.add_argument("--to", help="送り先の名前（default: 既定の送り先）")
    send_parser.set_defaults(func=send_command)

    queue_parser = subparsers.add_parser("queue", help="送信ジョブ")
    queue_sub = queue_parser.add_subparsers(dest="queue_command")
    list_parser = queue_sub.add_parser("list", parents=[common], help="送信ジョブと履歴を出す")
    list_parser.add_argument("--status", choices=QUEUE_STATUS_CHOICES, help="状態で絞る")
    list_parser.set_defaults(func=queue_list_command)
    retry_parser = queue_sub.add_parser("retry", parents=[common], help="失敗を再送する")
    retry_target = retry_parser.add_mutually_exclusive_group(required=True)
    retry_target.add_argument("--all", action="store_true", help="失敗の全部")
    retry_target.add_argument(
        "--job", type=int, help="送信ジョブの ID（送信完了の件は、新しい件として全部を送り直す）"
    )
    retry_target.add_argument(
        "--stale", action="store_true", help="送信中のまま止まった件の全部（失敗に戻して送る）"
    )
    retry_parser.set_defaults(func=queue_retry_command)

    commit_parser = subparsers.add_parser(
        "commit", parents=[common], help="送った検査の保管の確認を求めて待つ（Phase 3c）"
    )
    commit_parser.add_argument("--job", type=int, required=True, help="送信ジョブの ID（送信完了の件）")
    commit_parser.add_argument(
        "--wait",
        type=_positive_seconds,
        help="結果を待つ秒（default: 送り先の commitment_timeout_seconds）",
    )
    commit_parser.set_defaults(func=commit_command)

    mpps_parser = subparsers.add_parser("mpps", help="MPPS の送信ジョブ（Phase 3c）")
    mpps_sub = mpps_parser.add_subparsers(dest="mpps_command")
    mpps_list_parser = mpps_sub.add_parser("list", parents=[common], help="MPPS の知らせを出す")
    mpps_list_parser.set_defaults(func=mpps_list_command)
    mpps_retry_parser = mpps_sub.add_parser(
        "retry", parents=[common], help="送信に失敗した MPPS を再送する"
    )
    mpps_retry_parser.set_defaults(func=mpps_retry_command)


ZERO_ITEMS_MESSAGE = "予約はありません。条件を広げるか、緊急の患者で撮ってください"
NON_ASCII_HINT = (
    "日本語の条件は相手の文字コードの扱いに左右されます。患者 ID か受付番号でも取得してください"
)


def echo_command(args: argparse.Namespace) -> int:
    service = _service(args)
    result = service.echo(destination=args.to, worklist=args.worklist)
    if args.json:
        _print_json(result.model_dump())
    else:
        _emit(
            f"C-ECHO {result.ae_title} ({result.host}:{result.port}): "
            f"つながった（{result.elapsed_ms} ms）"
        )
    return 0


def worklist_query_command(args: argparse.Namespace) -> int:
    service = _service(args)
    query = _build_query(service, args)
    result = service.query_worklist(query)
    if args.json:
        _print_json(
            {
                "worklist": service.config.worklist.ae_title,
                "response_character_set": result.response_character_set,
                "partial": result.partial,
                "items": [item.model_dump() for item in result.items],
            }
        )
        return 0
    _print_worklist(service, result)
    return 0


def worklist_show_command(args: argparse.Namespace) -> int:
    item = _service(args).find_item(args.key)
    if args.json:
        _print_json(item.model_dump())
        return 0
    for name, value in item.model_dump().items():
        if name == "sequences":
            value = ", ".join(value) or "-"
        elif isinstance(value, list):
            value = "\\".join(value) or "-"
        _emit(f"{name:40s} {value}")
    return 0


def exam_command(args: argparse.Namespace) -> int:
    service = _service(args)
    images = _parse_images(args.images, args.series)
    emergency_patient = None
    if args.emergency:
        if not args.patient_id or not args.patient_name:
            raise ConfigurationError("--emergency requires --patient-id and --patient-name")
        emergency_patient = ScheduledPatient(
            patient_id=args.patient_id,
            patient_name=args.patient_name,
            birth_date=args.birth_date or "",
            sex=args.sex or "",
        )
    elif args.study_description:
        raise ConfigurationError("--study-description is only for --emergency")

    result = service.exam(
        ExamRequest(
            worklist_key=args.from_worklist,
            refresh=args.refresh,
            emergency_patient=emergency_patient,
            study_description=args.study_description or "",
            template=args.modality,
            profile=args.profile,
            hospital=args.hospital,
            images_per_series=images,
            pixel_mode=args.pixel_mode,
            abnormal_level=args.abnormal_level,
            charset=args.charset,
            output_dir=args.output,
            mpps=args.mpps,
        )
    )
    if result.mpps is not None and not result.mpps.sent:
        # MPPS を送れなくても撮影は止めない（8.4。終了コードは変えない）
        _emit(
            f"[WARN] MPPS {result.mpps.state} not sent: {result.mpps.error} "
            "(python -m app.cli mpps retry)",
            file=sys.stderr,
        )
    send_result = service.send(result.output_dir, args.to) if args.send else None

    if args.json:
        payload: dict[str, Any] = result.model_dump()
        payload["send"] = send_result.model_dump() if send_result else None
        _print_json(payload)
    else:
        for notice in result.notices:
            _emit(f"[NOTICE] {notice}")
        _emit(
            f"Exam completed: {result.output_dir} ({len(result.files)} files, "
            f"SpecificCharacterSet: {_charset_label(result.character_set)})"
        )
        if send_result:
            _print_send_result(send_result)
    if send_result:
        _raise_if_failed([send_result])
    return 0


def send_command(args: argparse.Namespace) -> int:
    result = _service(args).send(args.folder, args.to)
    if args.json:
        _print_json(result.model_dump())
    else:
        _print_send_result(result)
    _raise_if_failed([result])
    return 0


def queue_list_command(args: argparse.Namespace) -> int:
    jobs = _service(args).list_queue(args.status)
    if args.json:
        _print_json([job.model_dump() for job in jobs])
        return 0
    # 元のファイルのフォルダは既定では出さない。-v で最後の列に足す
    folder_header = "  FOLDER" if args.verbose else ""
    _emit(
        f"{'ID':>4}  {'STATUS':8s} {'PATIENT_ID':12s} {'ACCESSION':12s} {'DEST':12s} "
        f"{'SENT':>9}  {'COMMIT':9s}  {'UPDATED':19s}{folder_header}"
    )
    for job in jobs:
        sent = f"{job.num_sent}/{job.num_files}"
        commitment = job.commitment or "-"
        folder = f"  {job.folder}" if args.verbose else ""
        _emit(
            f"{job.id:>4}  {job.status:8s} {job.patient_id or '-':12s} "
            f"{job.accession_number or '-':12s} {job.destination:12s} {sent:>9}  "
            f"{commitment:9s}  {job.updated_at:19s}{folder}{STALE_MARK if job.stale else ''}"
        )
    _emit(f"[INFO] {len(jobs)} job(s).")
    return 0


def commit_command(args: argparse.Namespace) -> int:
    """保管の確認を求め、待ち受けで結果を待つ（11.8）。確認済でなければ終了コード 5."""
    state = _service(args).commit_and_wait(args.job, args.wait)
    if args.json:
        _print_json(state.model_dump())
    else:
        _emit(
            f"Storage commitment job {state.job_id} to {state.destination}: {state.status} "
            f"({state.num_confirmed}/{state.num_requested} confirmed)"
        )
    if state.status != "confirmed":
        raise StorageCommitmentError(
            f"Storage commitment is {state.status}",
            {"job_id": state.job_id, "reason": state.error or "no result yet"},
        )
    return 0


def mpps_list_command(args: argparse.Namespace) -> int:
    records = _service(args).list_mpps()
    if args.json:
        _print_json([{**record.model_dump(), "sent": record.sent} for record in records])
        return 0
    _emit(f"{'ID':>4}  {'STATE':12s} {'SENT':6s} {'ACCESSION':16s} {'UPDATED':19s}  ERROR")
    for record in records:
        _emit(
            f"{record.id:>4}  {record.state:12s} {_sent_label(record.sent):6s} "
            f"{record.accession_number or '-':16s} {record.updated_at:19s}  "
            f"{'' if record.sent else record.last_error}"
        )
    _emit(f"[INFO] {len(records)} MPPS record(s).")
    return 0


def mpps_retry_command(args: argparse.Namespace) -> int:
    records = _service(args).retry_mpps()
    if args.json:
        _print_json([{**record.model_dump(), "sent": record.sent} for record in records])
    else:
        for record in records:
            _emit(f"MPPS {record.id} {record.state}: {_sent_label(record.sent)}")
        _emit(f"[INFO] {len(records)} MPPS record(s) retried.")
    return 0


def queue_retry_command(args: argparse.Namespace) -> int:
    results = _service(args).retry(job_id=args.job, all_failed=args.all, stale=args.stale)
    if args.json:
        _print_json([result.model_dump() for result in results])
    else:
        for result in results:
            _print_send_result(result)
        _emit(f"[INFO] {len(results)} job(s) retried.")
    _raise_if_failed(results)
    return 0


def _service(args: argparse.Namespace) -> ModalityService:
    pynetdicom_level = logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING
    logging.getLogger("pynetdicom").setLevel(pynetdicom_level)
    # `--station` はこのコマンドだけに効き、画面で選んだ装置の記録は変えない（ADR-0023）
    return ModalityService(
        load_modality_config(Path(args.config)), station=getattr(args, "station", None)
    )


def _build_query(service: ModalityService, args: argparse.Namespace) -> WorklistQuery:
    config = service.config
    modality = args.modality or service.template_modality(config.default_template)
    station = args.station_aet or service.current_station().ae_title
    return WorklistQuery(
        date_range=parse_date_option(args.date, date.today()),
        modality="" if modality == ANY else modality,
        station_ae_title="" if station == ANY else station,
        patient_id=args.patient_id or "",
        patient_name=args.patient_name or "",
        accession_number=args.accession or "",
    )


def _print_worklist(service: ModalityService, result: WorklistQueryResult) -> None:
    _emit(
        f"[INFO] Worklist: {service.config.worklist.ae_title}  "
        f"SpecificCharacterSet: {_charset_label(result.response_character_set)}"
    )
    if not result.items:
        _emit(ZERO_ITEMS_MESSAGE)
        if result.query_non_ascii:
            _emit(NON_ASCII_HINT)
        return
    _emit(f"{'KEY':10s}  {'TIME':5s}  {'PATIENT_ID':10s}  {'ACCESSION':9s}  {'MODALITY':8s}  DESCRIPTION")
    for item in result.items:
        _emit(
            f"{item.key:10s}  {_time(item.scheduled_start_time):5s}  {item.patient_id:10s}  "
            f"{item.accession_number:9s}  {item.modality:8s}  "
            f"{item.requested_procedure_description}{_item_marks(service, item)}"
        )
    if result.partial:
        _emit("[WARN] 途中まで（相手が返し続けたため C-CANCEL を送った）")
    state = Path(service.config.state_dir) / "worklist_last.json"
    _emit(f"[INFO] {len(result.items)} item(s). Saved to {state}")


def _item_marks(service: ModalityService, item: WorklistItem) -> str:
    marks = []
    own_ae_title = service.current_station().ae_title
    if item.scheduled_station_ae_title and item.scheduled_station_ae_title != own_ae_title:
        marks.append("別の装置")
    if item.unreadable_attributes:
        marks.append("読めない値")
    groups = item.patient_name.split("=")
    if len(groups) < 2 or not any(group for group in groups[1:]):
        marks.append("漢字・かなが空")
    return f"  [{' / '.join(marks)}]" if marks else ""


def _print_send_result(result: SendResult) -> None:
    sent = sum(1 for r in result.results if r.sent)
    _emit(
        f"Send job {result.job_id} to {result.destination}: {result.status} "
        f"({sent}/{len(result.results)} files)"
    )
    for failure in (r for r in result.results if not r.sent):
        _emit(f"[ERROR] {failure.path}: {failure.reason}", file=sys.stderr)
    if result.error and not result.results:
        _emit(f"[ERROR] {result.error}", file=sys.stderr)


def _raise_if_failed(results: list[SendResult]) -> None:
    failed = [result for result in results if result.status != "sent"]
    if failed:
        first = failed[0]
        reason = next((r.reason for r in first.results if not r.sent), first.error)
        raise StoreError(
            "Some images were not sent",
            {"jobs": ", ".join(str(result.job_id) for result in failed), "reason": reason},
        )


def _parse_images(images: str | None, series: int) -> list[int]:
    """`-i` を省いたら、どのシリーズも DEFAULT_IMAGES_PER_SERIES 枚にする."""
    if images is None:
        if series < 1:
            raise ConfigurationError("Series count must be at least 1", {"series": series})
        return [DEFAULT_IMAGES_PER_SERIES] * series
    try:
        values = [int(value.strip()) for value in images.split(",")]
    except ValueError as exc:
        raise ConfigurationError(
            "Images must be comma-separated integers", {"images": images}
        ) from exc
    if any(value <= 0 for value in values):
        raise ConfigurationError("Each image count must be greater than 0", {"images": images})
    if len(values) != series:
        raise ConfigurationError(
            "Series count and image list length do not match",
            {"series": series, "images_count": len(values)},
        )
    return values


def _sent_label(sent: bool) -> str:
    return "sent" if sent else "unsent"


def _positive_seconds(value: str) -> float:
    """`commit --wait` の秒（1 以上）."""
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if seconds < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return seconds


def _charset_label(character_set: list[str]) -> str:
    return "\\".join(character_set) if character_set else "(default)"


def _time(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}" if len(value) >= 4 else value


def _print_json(data: Any) -> None:
    print(json_for_terminal(data))


def _emit(*values: object, file: TextIO | None = None) -> None:
    """相手から来る値を含む行を、制御文字を見える形にしてから出す（11.7）."""
    print(*(sanitize_for_terminal(str(value)) for value in values), file=file)
