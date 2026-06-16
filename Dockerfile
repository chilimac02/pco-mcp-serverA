# PCO MCP Server — production image
#
# Build:
#   docker build -t pco-mcp:latest .
#
# Run (replace ./db with a persistent host path like /mnt/data/pco-mcp/db):
#   docker run --rm -p 8011:8011 --env-file .env -v ./db:/app/db pco-mcp:latest

# ---------------------------------------------------------------------------
# Use 3.12-slim per the project plan. The deps tree (httpx, mcp, cryptography,
# aiosqlite, fastapi, uvicorn[standard]) all publish manylinux wheels for
# 3.12 so no compilers are needed.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Logs flush immediately (no buffering); no .pyc files inside the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so layer caches survive code edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source. .dockerignore keeps tests, .env, the host venv, etc. out.
COPY app/ ./app/

# Create the db directory the SQLite migrator will write to. Mount over
# this with a host volume in production so sessions survive restarts.
# Run as a non-root user (security: limits blast radius if the app is ever
# compromised) but make sure that user owns /app/db.
RUN mkdir -p /app/db && \
    useradd --create-home --shell /usr/sbin/nologin --uid 1000 pco && \
    chown -R pco:pco /app

USER pco

EXPOSE 8011

# Healthcheck hits /health every 30s. Uses Python (already present) instead
# of curl, so we don't have to apt-get install anything just for this.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8011/health', timeout=5).status == 200 else 1)" \
    || exit 1

# Bind 0.0.0.0 inside the container so port-forwarding works from the host.
# --forwarded-allow-ips='*' tells uvicorn to trust X-Forwarded-* (and the
# Host header) from any client. Without this, uvicorn 0.34+ returns
# 421 Misdirected Request when a proxy (Cloudflare Tunnel, NPM, etc.)
# forwards requests with a Host header that doesn't match the bind address.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011", "--forwarded-allow-ips", "*"]
