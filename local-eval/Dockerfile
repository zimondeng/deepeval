# 3.11-slim is already on this machine. typesafe-sdk 0.7.5 needs Python >= 3.10.
# Pulling 3.12 would need Docker Hub, which this daemon cannot reach.
FROM docker:cli AS docker-cli

FROM python:3.11-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/eval \
    DEEPEVAL_TELEMETRY_OPT_OUT=1

WORKDIR /opt/src

COPY pyproject.toml README.md ./
COPY deepeval ./deepeval
RUN pip install --no-cache-dir .

COPY local-eval/evals /eval/evals
COPY local-eval/ui /eval/ui
COPY local-eval/datasets /eval/datasets
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN mkdir -p /eval/reports

WORKDIR /eval
CMD ["python", "-m", "evals.test_smoke"]
