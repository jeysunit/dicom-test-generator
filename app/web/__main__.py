"""`python -m app.web`：画面を起動する（docs/spec/12a_web_screens_and_cli.md 10.9、docs/spec/12_modality_emulator.md 12 章）.

終了コード：0=正常に止めた、2=設定の誤り（手元の外でパスワードが無いなどを含む）。
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from app.core.exceptions import ConfigurationError, ModalityConfigError
from app.core.text_safety import make_visible

from .app import create_app
from .auth import PASSWORD_FILE_ENV, USERNAME, startup_password
from .settings import load_app_config

DEFAULT_CONFIG = "config/app_config.yaml"
EXIT_OK = 0
EXIT_CONFIG_ERROR = 2

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.web",
        description="モダリティエミュレータのウェブ画面を起動する（既定は手元の 127.0.0.1:8080）",
        epilog=(
            f"手元の外で待ち受けるときは {PASSWORD_FILE_ENV} にパスワードのファイルを指す"
            f"（利用者の名前は {USERNAME}）。TLS は前段の逆プロキシで付ける。"
        ),
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG, help=f"設定ファイル（default: {DEFAULT_CONFIG}）"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("pynetdicom").setLevel(logging.WARNING)

    config_path = Path(args.config)
    try:
        modality, web = load_app_config(config_path)
        password = startup_password(web.bind_address)
    except (ConfigurationError, ModalityConfigError) as exc:
        print(f"[ERROR] {make_visible(str(exc))}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    app = create_app(modality, config_path=config_path, web=web, password=password)
    auth = "HTTP Basic" if password is not None else "none (localhost only)"
    logger.info("Web UI on http://%s:%s/ (auth: %s)", web.bind_address, web.port, auth)
    uvicorn.run(app, host=web.bind_address, port=web.port, log_level="info")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
