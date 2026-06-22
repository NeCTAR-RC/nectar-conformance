# syntax=docker/dockerfile:1
# Single image for both the web Deployment (nectar-conformance-web) and the refresh
# CronJob (nectar-conformance-refresh) -- same image, different command.

# --- Stage 1: build the SPA -------------------------------------------------
FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime ------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NECTAR_CONFORMANCE_WEB_STATIC=/app/web-static \
    NECTAR_CONFORMANCE_REPORTS_DIR=/var/lib/nectar-conformance
WORKDIR /app

# Install the package with the web extra. Only the bits pip needs are copied.
# setuptools-scm derives the version from git, but .git is not in the build
# context, so the Makefile passes the git-derived version in and we hand it to
# setuptools-scm. ARG (not ENV) keeps it out of the final image's environment.
ARG VERSION
COPY pyproject.toml README.md ./
COPY nectar_conformance/ ./nectar_conformance/
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NECTAR_CONFORMANCE="$VERSION" pip install '.[web]'

# Drop in the built SPA; load_settings() picks it up via NECTAR_CONFORMANCE_WEB_STATIC.
COPY --from=frontend /build/dist/ /app/web-static/

# Run unprivileged. The reports dir is the PVC mount point in k8s; created here so
# local runs work too.
RUN useradd --system --uid 10001 app \
    && mkdir -p /var/lib/nectar-conformance \
    && chown -R app:app /var/lib/nectar-conformance
USER app

EXPOSE 8080
CMD ["nectar-conformance-web", "--host", "0.0.0.0", "--port", "8080"]
