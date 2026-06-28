FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget openssh-client openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data /var/log/fvpn

EXPOSE 8000

# --proxy-headers: trust X-Forwarded-Proto/Host from nginx
# --forwarded-allow-ips "*": accept proxy headers from any upstream (nginx is in same docker network)
# Without --proxy-headers, uvicorn sees plain HTTP from nginx → generates http:// redirects
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
