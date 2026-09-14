# Multi-arch Python 3.12.14 / Alpine 3.24 image, pinned by index digest.
FROM python:3.12.14-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    DB_PATH=/data/haushaltpro.db \
    HOST=0.0.0.0 \
    PORT=8080

# Apply Alpine security updates available after the pinned base-image snapshot.
RUN apk upgrade --no-cache

WORKDIR /app
COPY requirements.txt ./
# pip/setuptools/ensurepip are build tooling only. Remove them from the final
# runtime filesystem after dependency validation so vendored packages in those
# tools cannot add an unnecessary runtime attack surface or stale SBOM entries.
RUN python -m pip install --no-cache-dir --disable-pip-version-check --upgrade "pip==26.2" \
    && python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && python -m pip check \
    && rm -rf \
       /usr/local/lib/python3.12/site-packages/pip \
       /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
       /usr/local/lib/python3.12/site-packages/setuptools \
       /usr/local/lib/python3.12/site-packages/setuptools-*.dist-info \
       /usr/local/lib/python3.12/site-packages/_distutils_hack \
       /usr/local/lib/python3.12/site-packages/pkg_resources \
       /usr/local/lib/python3.12/site-packages/wheel \
       /usr/local/lib/python3.12/site-packages/wheel-*.dist-info \
       /usr/local/lib/python3.12/ensurepip \
       /usr/local/bin/pip \
       /usr/local/bin/pip3 \
       /usr/local/bin/pip3.12 \
    && python -c "import fastapi,starlette,uvicorn,pydantic,argon2,cryptography,multipart; from sqlcipher3 import dbapi2 as sqlite; c=sqlite.connect(':memory:'); v=c.execute('PRAGMA cipher_version').fetchone()[0]; assert str(v).startswith('4.')"
COPY app ./app
COPY static ./static
RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -u 10001 -G appuser -h /home/appuser appuser \
    && mkdir -p /data /home/appuser \
    && chown -R appuser:appuser /app /data /home/appuser

USER 10001:10001
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--no-access-log","--no-server-header","--workers","1","--limit-concurrency","100","--limit-max-requests","10000","--timeout-keep-alive","5"]
