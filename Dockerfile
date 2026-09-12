# Current multi-arch Python 3.12.14 / Debian Bookworm image, pinned by index digest.
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    DB_PATH=/data/haushaltpro.db \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY app ./app
COPY static ./static
RUN useradd --system --uid 10001 --create-home --home-dir /home/appuser appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER 10001:10001
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--no-access-log","--no-server-header","--workers","1","--limit-concurrency","100","--limit-max-requests","10000","--timeout-keep-alive","5"]
