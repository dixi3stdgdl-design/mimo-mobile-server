FROM python:3.13-slim

RUN groupadd -r mimo && useradd -r -g mimo -d /app -m -s /bin/bash mimo

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create data directory with proper permissions
RUN mkdir -p /data && chown mimo:mimo /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=mimo:mimo config.py protocol.py state.py metrics.py http_handler.py server.py auth.py tls_config.py analytics.py b2b.py b2b_api.py ./
COPY --chown=mimo:mimo handlers/ handlers/

USER mimo

EXPOSE 8765 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

CMD ["python3", "server.py"]
