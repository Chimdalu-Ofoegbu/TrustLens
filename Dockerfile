FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY indexer/ indexer/
COPY scoring/ scoring/
COPY server/ server/
COPY web/ web/
COPY data/okx-marketplace-census-2026-07-10.csv data/
RUN pip install --no-cache-dir .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
# Dual [ -f ... ] guard self-seeds BOTH the DB and the leaderboard from the committed census CSV inside the container (offline, seconds, byte-deterministic) so images are reproducible and never bake a stale local DB.
CMD ["/bin/sh", "-c", "[ -f data/trustlens.db ] && [ -f web/dist/index.html ] || python -m indexer.refresh; exec uvicorn server.main:app --host 0.0.0.0 --port 8000"]
