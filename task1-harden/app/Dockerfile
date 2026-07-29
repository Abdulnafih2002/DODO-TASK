# syntax=docker/dockerfile:1
# Hardened multi-stage build for ledger-api.
#   * Multi-stage: build deps in a builder, ship only the venv + app.
#   * Non-root (UID 10001) baked into the image so the container cannot start as root.
#   * No shell/package manager needed at runtime; slim base kept patched.
#   * Runs under gunicorn (production WSGI) rather than Flask's dev server.
# NOTE: pin the base by digest in CI (docker buildx --provenance) for reproducibility.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
# Create an unprivileged user; the k8s securityContext also enforces runAsNonRoot.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY app.py .
USER 10001:10001
EXPOSE 8080
# 2 workers, bind all interfaces on 8080; access log to stdout.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--access-logfile", "-", "app:app"]
