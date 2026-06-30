# Stage 0: source the official Docker CLI binary (no apt repo, no signing key drama)
FROM docker:cli AS dockercli

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget openssh-client openssl \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI — required for /api/system/{xray,singbox}/restart and for
# config_writer's auto-reload to work. The backend talks to the HOST's
# Docker daemon via the socket mounted in docker-compose.yml
# (/var/run/docker.sock) and restarts the sibling fvpn-xray / fvpn-singbox
# containers directly. Without this binary, every restart call returns 500.
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data /var/log/fvpn

EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
