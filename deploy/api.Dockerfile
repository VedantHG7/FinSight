FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NUMBA_CACHE_DIR=/tmp/numba-cache

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --only-binary=:all: -r requirements.txt

RUN groupadd --gid 10001 finsight \
    && useradd --uid 10001 --gid finsight --create-home finsight \
    && mkdir -p /data/analyses /data/storage \
    && chown -R finsight:finsight /data

COPY --chown=finsight:finsight backend/main.py ./main.py
COPY --chown=finsight:finsight backend/app ./app
USER finsight
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
