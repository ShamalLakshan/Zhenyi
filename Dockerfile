# ── Lean Python Runtime ────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime performance & storage optimization flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DB_PATH=/app/data/zhenyi.db \
    LOG_DIR=/app/logs

WORKDIR /app

# Create dedicated non-root user (UID 1000 for standard rootless compatibility)
RUN groupadd -g 1000 zhenyi && \
    useradd -u 1000 -g zhenyi -m -s /bin/bash zhenyi && \
    mkdir -p /app/data /app/logs /app/web-ui/dist && \
    chown -R zhenyi:zhenyi /app

# Install Python dependencies without caching wheel archives to conserve disk
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip /tmp/*

# Copy backend application source files
COPY --chown=zhenyi:zhenyi agents/ ./agents/
COPY --chown=zhenyi:zhenyi core/ ./core/
COPY --chown=zhenyi:zhenyi scrapers/ ./scrapers/
COPY --chown=zhenyi:zhenyi server.py agents.yaml .env.example pyproject.toml LICENSE README.md ./

# Copy compiled frontend distribution
COPY --chown=zhenyi:zhenyi web-ui/dist/ ./web-ui/dist/

# Define persistent mount points for database state and telemetry logs
VOLUME ["/app/data", "/app/logs"]

# Expose default HTTP/WebSocket server port
EXPOSE 8000

# Zero-dependency healthcheck using Python's built-in urllib (no curl required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

# Run as non-root user
USER zhenyi

# Start single-worker Uvicorn process to minimize background CPU/RAM footprint
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
