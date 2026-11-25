FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ressy_server ./ressy_server

RUN useradd --create-home --uid 10001 ressy \
    && mkdir -p /data \
    && chown ressy:ressy /data

USER ressy

ENV RESSY_DB_PATH=/data/ressy.db \
    RESSY_HOST=0.0.0.0 \
    RESSY_PORT=8765

EXPOSE 8765
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "ressy_server"]
