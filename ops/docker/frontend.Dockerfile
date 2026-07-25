# Multi-stage build: stage 1 builds the Vite/React source under
# `src/frontend/`, stage 2 serves the resulting static bundle from Nginx.
#
# The legacy `src/frontend-dist/` bundle path is no longer referenced — the
# frontend is now produced by `npm run build` inside the build stage.

FROM node:22-alpine AS build
WORKDIR /app

# Install dependencies first (cacheable layer keyed on package files).
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the frontend source and build.
COPY src/frontend/ ./
RUN npm run build


FROM nginx:1.29-alpine

# Version metadata for nexainer/`docker inspect` visibility (the UI itself
# reads the running version from the backend's /api/version).
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG APP_VERSION=dev
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.created=$BUILD_TIME \
      org.opencontainers.image.source=https://github.com/dannybergt/trading-bot-v2

COPY ops/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
