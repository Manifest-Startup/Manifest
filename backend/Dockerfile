# Manifest Backend — hardened production image.
# Task #16 (Supply chain, CI/CD & responsible disclosure).
#
# Hardening summary:
#   - Multi-stage build (builder + runtime) so build tooling does not ship to
#     production.
#   - Non-root runtime user (`app`, uid 10001).
#   - `tini` as PID 1 for proper signal handling.
#   - HEALTHCHECK against /health.
#   - Minimal apt footprint; --no-install-recommends + cache cleanup; rootfs
#     is read-only at runtime (writable /tmp via tmpfs at orchestrator).
#   - PYTHONDONTWRITEBYTECODE + PYTHONUNBUFFERED for predictable behaviour.
#   - OCI labels for provenance + SBOM linking.
#
# Base image is pinned by digest. The digest is bumped by Dependabot
# ("docker" ecosystem) and reviewed by @Manifest-Startup/security per
# CODEOWNERS. The trailing tag comment is informational only.
#
# Verification of this image happens in .github/workflows/security.yml
# (hadolint + trivy) and again at deploy time per RELEASE_PLAYBOOK.md.

# --- Stage 1: build ---------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build-time OS deps in a single layer; clean apt lists.
# We deliberately do NOT run `apt-get upgrade` here: the base image is
# digest-pinned (FROM ...@sha256:...) so the package set is already
# fully determined at image-build time. Re-upgrading would reintroduce
# time-dependent variance and break reproducible-build guarantees.
# Base-image CVE rolls happen via Dependabot bumping the FROM digest,
# reviewed by @Manifest-Startup/security per CODEOWNERS.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ca-certificates; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Install Python deps into an isolated prefix we copy into the runtime image.
COPY requirements.txt ./
RUN pip install --upgrade pip==24.2 \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime

# OCI labels — used by SBOM tooling and the trust center.
LABEL org.opencontainers.image.title="manifest-backend" \
      org.opencontainers.image.description="Manifest API server (FastAPI + Strawberry GraphQL + Socket.IO)" \
      org.opencontainers.image.vendor="Manifest Startup" \
      org.opencontainers.image.source="https://github.com/Manifest-Startup/Manifest" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.documentation="https://github.com/Manifest-Startup/Manifest/blob/main/docs/security/RELEASE_PLAYBOOK.md" \
      io.manifest.security.policy="https://github.com/Manifest-Startup/Manifest/blob/main/SECURITY.md"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages"

# Runtime OS deps only (libpq for psycopg2, tini for PID 1, ca-certificates).
# `apt-get upgrade` intentionally omitted — see the build-stage rationale
# above. Reproducibility > drive-by upgrade.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        libpq5 \
        tini \
        ca-certificates; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Create the non-root user up-front so we can chown installed files.
RUN groupadd --system --gid 10001 app \
 && useradd  --system --uid 10001 --gid app \
             --home-dir /app --shell /usr/sbin/nologin app

# Copy the prebuilt site-packages from the builder stage.
COPY --from=builder /install /install

# Copy application code with restrictive ownership.
WORKDIR /app
COPY --chown=app:app . /app

# The backend resolves generated assets from the repository root. In this
# backend-only image that root is `/`, so create the writable path explicitly.
# Cloudflare staging treats it as ephemeral; durable file migration remains a
# cutover gate in docs/CLOUDFLARE_MIGRATION.md.
RUN mkdir -p /generated/pdfs \
 && chown -R app:app /generated

# Drop privileges. /tmp is writable for FastAPI / Uvicorn working files;
# orchestrator should mount it as tmpfs and run with read-only root FS.
USER app:app

EXPOSE 8000

# Healthcheck — backend exposes GET /ping (see backend/app/main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/ping', timeout=4).status == 200 else sys.exit(1)" \
  || exit 1

# Trusted-proxy CIDRs are supplied by the orchestrator at deploy time via the
# UVICORN_FORWARDED_ALLOW_IPS env var (e.g. the platform load-balancer's
# private subnet). The image refuses to default to "*" — trusting forwarded
# headers from any source allows source-IP / X-Forwarded-* spoofing, which
# would defeat audit logging, rate limiting, and step-up auth.
ENV UVICORN_FORWARDED_ALLOW_IPS="127.0.0.1"

ENTRYPOINT ["/usr/bin/tini", "--"]
# WEB_CONCURRENCY controls the uvicorn worker count (default 1 — unchanged
# behaviour). With the event loop no longer blocked on LLM/DB calls (Phase 2),
# raise it to ~ (2 * vCPU) on the Render instance for real request parallelism.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"${WEB_CONCURRENCY:-1}\" --proxy-headers --forwarded-allow-ips=\"${UVICORN_FORWARDED_ALLOW_IPS}\""]
