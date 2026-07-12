# Build the browser client separately so the runtime image only contains
# production assets and Python dependencies.
FROM node:22-bookworm-slim AS frontend

WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates lib32gcc-s1 lib32stdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY support/ ./support/
COPY Palworld_Server.py ./
COPY --from=frontend /src/web/dist ./web/dist
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --shell /bin/bash autopal \
    && mkdir -p /data /servers \
    && chown -R autopal:autopal /data /servers \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER root
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/auth/status', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
