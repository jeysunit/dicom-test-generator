# syntax=docker/dockerfile:1
# dicom-test-generator のイメージ（モダリティのダミーの CLI と Web 画面）。
#
# - 土台は Python の公式のイメージ（slim）。GUI（PySide6）と試験の包みは入れない
# - root でない利用者（dtg、uid 10001）で動かす。コードは root のもののまま（dtg からは読むだけ）
# - 設定は外から /app/config/app_config.yaml に mount する（イメージの中の設定は例）
# - Web 画面はコンテナの中で 0.0.0.0 に bind するので、設定の web.bind_address を
#   "0.0.0.0" にし、HTTP Basic のパスワードのファイルを DTG_WEB_PASSWORD_FILE で渡す
#   （README の「Docker で動かす」）
# - 書く場所：/app/modality_state（予約の結果・送信のキュー）、/app/output（作った画像）、
#   /app/logs（CLI のログ）

ARG PYTHON_IMAGE=python:3.12-slim-trixie

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依存は requirements.txt から入れる。GUI（PySide6・pytest-qt）と試験（pytest・httpx）の行だけを外す
COPY requirements.txt ./
RUN grep -viE '^(pyside6|pytest|pytest-qt|httpx)([<>=!~ ;#]|$)' requirements.txt > /tmp/requirements-runtime.txt \
  && pip install -r /tmp/requirements-runtime.txt \
  && rm /tmp/requirements-runtime.txt \
  && pip list --format=freeze

COPY app ./app
COPY config ./config
COPY data ./data
COPY examples ./examples
COPY profiles/examples ./profiles/examples
COPY templates ./templates

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin dtg \
  && mkdir -p logs modality_state output \
  && chown dtg:dtg logs modality_state output

USER 10001

EXPOSE 8080

CMD ["python", "-m", "app.web"]
