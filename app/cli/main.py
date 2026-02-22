"""CLI main module with argparse definitions."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from app.cli.commands import (
    generate_command,
    quick_command,
    validate_command,
    version_command,
)
from app.core import (
    ConfigurationError,
    DICOMGeneratorError,
    IOError as CoreIOError,
    ValidationError as CoreValidationError,
)

DEFAULT_LOG_FILE = "logs/dicom_generator.log"


def setup_logging(verbose: bool, quiet: bool, log_file: str) -> None:
    """CLIのログ設定を初期化する."""
    if quiet:
        console_level = logging.ERROR
    elif verbose:
        console_level = logging.DEBUG
    else:
        console_level = logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s")

    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def main() -> None:
    """CLIエントリポイント."""
    parser = _create_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    verbose = bool(getattr(args, "verbose", False))
    quiet = bool(getattr(args, "quiet", False))
    log_file = str(getattr(args, "log_file", DEFAULT_LOG_FILE))
    setup_logging(verbose=verbose, quiet=quiet, log_file=log_file)

    try:
        exit_code = int(args.func(args))
        sys.exit(exit_code)
    except Exception as exc:
        sys.exit(_map_exception_to_exit_code(exc))


_EPILOG = """\
使用例:
  python -m app.cli generate job.yaml
  python -m app.cli generate job.yaml -o output/ --verbose
  python -m app.cli generate job.yaml --dry-run
  python -m app.cli validate job.yaml
  python -m app.cli quick -p P000001 -m fujifilm_scenaria_view_ct -s 3 -i 1,20,20 -o output/
  python -m app.cli version

終了コード:
  0  成功
  1  一般エラー（生成失敗）
  2  設定エラー（Job YAML不正）
  3  ファイルI/Oエラー
  4  バリデーションエラー
"""


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="DICOMテストデータ生成CLI",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Job YAMLからDICOMを生成")
    generate_parser.add_argument("job_file", help="Job YAMLファイル")
    generate_parser.add_argument(
        "-o",
        "--output",
        help="出力先ディレクトリ（Job YAML設定を上書き）",
    )
    log_group = generate_parser.add_mutually_exclusive_group()
    log_group.add_argument("-v", "--verbose", action="store_true", help="詳細ログを表示")
    log_group.add_argument("-q", "--quiet", action="store_true", help="エラー以外を非表示")
    generate_parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"ログファイルパス（default: {DEFAULT_LOG_FILE}）",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="生成は行わず設定検証のみを実行",
    )
    generate_parser.set_defaults(func=generate_command)

    validate_parser = subparsers.add_parser("validate", help="Job YAMLを検証")
    validate_parser.add_argument("job_file", help="Job YAMLファイル")
    validate_parser.set_defaults(func=validate_command)

    quick_parser = subparsers.add_parser("quick", help="CLI引数のみで簡易生成")
    quick_parser.add_argument("-p", "--patient", required=True, help="患者ID")
    quick_parser.add_argument("-m", "--modality", required=True, help="モダリティテンプレート名")
    quick_parser.add_argument("-s", "--series", required=True, type=int, help="シリーズ数")
    quick_parser.add_argument(
        "-i",
        "--images",
        required=True,
        help="シリーズごとの画像数（カンマ区切り）例: 1,20,20",
    )
    quick_parser.add_argument("-o", "--output", required=True, help="出力先ディレクトリ")
    quick_parser.add_argument(
        "--accession-number",
        default="ACC000001",
        help="Accession Number",
    )
    quick_parser.add_argument(
        "--study-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="検査日（YYYYMMDD）",
    )
    quick_parser.add_argument("--hospital", help="病院テンプレート名")
    quick_parser.add_argument(
        "--pixel-mode",
        default="ct_realistic",
        help="ピクセルモード（simple_text / ct_realistic）",
    )
    quick_parser.set_defaults(func=quick_command)

    version_parser = subparsers.add_parser("version", help="バージョン表示")
    version_parser.set_defaults(func=version_command)

    return parser


def _map_exception_to_exit_code(exc: Exception) -> int:
    if isinstance(exc, ConfigurationError):
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    if isinstance(exc, CoreIOError):
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    if isinstance(exc, CoreValidationError):
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    if isinstance(exc, PydanticValidationError):
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 4
    if isinstance(exc, DICOMGeneratorError):
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[ERROR] {exc}", file=sys.stderr)
    return 1

