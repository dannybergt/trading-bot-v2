FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY src/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/backend/ /app/
# In-app help/doc markdown sources — read by docs_service at request time.
COPY docs/inapp/ /app/docs/inapp/

RUN mkdir -p /app/data && \
    useradd -m appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV DATA_DIR=/app/data

# Build/version metadata — passed by build.sh (derived from git). Baked into
# ENV (read by /api/version + /api/health) and OCI labels (visible via
# `docker inspect` and nexainer's inspect view). Declared late so a changed
# SHA only rebuilds these trivial layers, not the dependency install.
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG APP_VERSION=dev
ENV APP_GIT_SHA=$GIT_SHA \
    APP_BUILD_TIME=$BUILD_TIME \
    APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.created=$BUILD_TIME \
      org.opencontainers.image.source=https://github.com/dannybergt/trading-bot-v2

# Uvicorn trusts X-Forwarded-For/-Proto only from peers listed here; its own
# default is 127.0.0.1, which never matches because the only peer that can
# reach this container is the nginx frontend on a private compose network.
# Without this the forwarded headers are dropped and request.client.host stays
# the proxy address for every caller -- which silently collapses the per-client
# auth rate-limit buckets into one shared bucket and makes audit IP
# fingerprints useless. Trusting only private ranges keeps the value
# spoof-resistant: each hop appends, so a client-supplied public address ends
# up left of the real one and uvicorn returns the rightmost untrusted entry.
# Must stay in sync with docker-compose.yml (guarded by
# tests/test_forwarded_allow_ips.py).
ENV FORWARDED_ALLOW_IPS=127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
