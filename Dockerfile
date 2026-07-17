FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml .
COPY requirements-facilitator.txt .
COPY indexer/ indexer/
COPY scoring/ scoring/
COPY server/ server/
COPY web/ web/
COPY data/okx-marketplace-census-2026-07-10.csv data/
# The second file installs the deploy-time OKX x402 facilitator SDK (okxweb3-app-x402,
# base package only - pydantic + nest-asyncio + typing-extensions, no web3) so that
# server.payments._build_okx_facilitator's `from x402.http import ...` loads at runtime;
# unused until OKX creds make facilitator_ready() true and real settlement turns on.
RUN pip install --no-cache-dir . -r requirements-facilitator.txt
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/healthz').status==200 else 1)"
# Self-seeds BOTH the DB and the leaderboard from the committed census CSV inside the container (offline, seconds, byte-deterministic) so images are reproducible and never bake a stale local DB. Seeding failure aborts the boot (exit 1) so a bad deploy fails loudly here instead of as a confusing healthcheck timeout. Binds ${PORT:-8000}: Railway (and most PaaS) inject PORT and probe the app on it; locally PORT is unset so it falls back to 8000.
CMD ["/bin/sh", "-c", "if [ ! -f data/trustlens.db ] || [ ! -f web/dist/index.html ]; then python -m indexer.refresh || exit 1; fi; exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
