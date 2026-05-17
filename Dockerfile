# ── Stage 1: Builder ───────────────────────────────────────────
# Uses full Python image with build tools.
# This stage is DISCARDED — never ships to production.
# Its only job: install Python packages cleanly.
FROM python:3.11-slim AS builder
WORKDIR /app
COPY app/requirements.txt .
# --no-cache-dir: don't cache pip downloads (smaller layer)
# This layer is cached between builds if requirements.txt unchanged
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Production ────────────────────────────────────────
# Minimal base — no build tools, minimal attack surface.
# Only contains what's needed to RUN the app.
FROM python:3.11-slim AS production
WORKDIR /app

# Non-root user — security requirement.
# If container is compromised, attacker has limited privileges.
# Root in container = potential root escape on misconfigured hosts.
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser

# Copy installed packages from builder
# This is the multi-stage pattern: build in one, copy results to another
COPY --from=builder \
  /usr/local/lib/python3.11/site-packages \
  /usr/local/lib/python3.11/site-packages
COPY --from=builder \
  /usr/local/bin/uvicorn \
  /usr/local/bin/uvicorn

# Copy application code last
# Why last? Code changes most frequently.
# Layers above (system packages) are cached between deploys.
COPY app/main.py .

# Python behavior improvements for containers
ENV PYTHONDONTWRITEBYTECODE=1  \
    PYTHONUNBUFFERED=1

# Build arguments allow CI to inject metadata
ARG APP_VERSION=1.0.0
ARG APP_COLOR=blue
ARG GIT_COMMIT=unknown
ARG BUILD_TIME=unknown

ENV APP_VERSION=$APP_VERSION \
    APP_COLOR=$APP_COLOR \
    GIT_COMMIT=$GIT_COMMIT \
    BUILD_TIME=$BUILD_TIME

USER appuser
EXPOSE 8000

# Single process per container
# Kubernetes scales by adding MORE pods, not more processes
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
