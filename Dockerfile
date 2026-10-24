# syntax=docker/dockerfile:1
# dicom-test-generator のイメージ（モダリティエミュレーターの CLI と Web 画面）。
#
# - ベースイメージは Python の公式イメージ（slim）。テスト用のパッケージは入れない
# - root 以外のユーザー（dtg、uid 10001）で動かす。コードの所有者は root のまま（dtg は読み取りだけ）。
#   --user で任意の UID・GID を指定しても動く（書き込む場所は 1777）
# - イメージの中の設定は、リポジトリの設定の例の web.bind_address を "0.0.0.0" にしたもの。
#   0.0.0.0 で待ち受けるので、HTTP Basic のパスワードのファイルを DTG_WEB_PASSWORD_FILE で
#   渡さなければ起動しない（docs/usage.md の 1 章）。設定を変えるときは
#   /app/config/app_config.yaml に mount する
# - 書き込む場所：/app/modality_state（予約の結果・送信キュー）、/app/output（作成した画像）、
#   /app/logs（CLI のログ）

# ベースイメージは digest で固定する（マルチアーキテクチャの manifest list の digest。
# 2026-10-24 に docker buildx imagetools inspect で確認した）。更新するときも同じ方法で確認する
ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依存は requirements.txt から入れる。テスト用（pytest・httpx）の行だけを除外する
COPY requirements.txt ./
RUN grep -viE '^(pytest|httpx)([<>=!~ ;#]|$)' requirements.txt > /tmp/requirements-runtime.txt \
  && pip install -r /tmp/requirements-runtime.txt \
  && rm /tmp/requirements-runtime.txt \
  && pip list --format=freeze

COPY app ./app
COPY config ./config
COPY data ./data
COPY examples ./examples
COPY profiles/examples ./profiles/examples
COPY templates ./templates

# web: の節の bind_address だけを 0.0.0.0 にする。書き換えられなければビルドを失敗させる
RUN awk '/^web:/ { web = 1 } web && /bind_address:/ { sub(/"127\.0\.0\.1"/, "\"0.0.0.0\"") } { print }' \
    config/app_config.yaml > /tmp/app_config.yaml \
  && grep -A2 '^web:' /tmp/app_config.yaml | grep -q 'bind_address: "0.0.0.0"' \
  && cp /tmp/app_config.yaml config/app_config.yaml

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin dtg \
  && mkdir -p logs modality_state output \
  && chown dtg:dtg logs modality_state output \
  && chmod 1777 logs modality_state output

USER 10001

EXPOSE 8080

CMD ["python", "-m", "app.web"]
