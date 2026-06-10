# CLEARANCE demo backend — pure-Python FastAPI. Runtime is in-memory (BM25 + dense
# numpy) over the synthetic Meridian corpus: NO surreal binary, NO turbovec, NO live
# provider creds needed (verified: boots + serves governed queries with neither). The
# synthetic demo_profile refuses to start if any live source/cred is present.
FROM python:3.12-slim AS base

# non-root user
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# install runtime deps first (layer cache); copy only what's needed to install.
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# app source + the synthetic corpus baked into the image
COPY src/ ./src/
COPY corpus/ ./corpus/
COPY seeds/ ./seeds/
RUN pip install --no-cache-dir --no-deps -e . \
 && chown -R appuser:appuser /app

USER appuser

# GATE B: the demo ships the SAFE profile — synthetic-only (refuse-to-start on any live
# source/cred), abuse caps on. No live LLM/embedding/DB creds in the image.
ENV RAG_DEMO_PROFILE=synthetic \
    RAG_CORPUS_DIR=/app/corpus \
    RAG_STORE_BACKEND=memory \
    RAG_RATE_LIMIT_PER_MIN=30 \
    RAG_INSTANCE_RATE_LIMIT_PER_MIN=1500 \
    RAG_QUERY_CAP_PER_DAY=500 \
    PORT=8000

# healthcheck on /health (the liveness endpoint)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health'; \
sys.exit(0 if urllib.request.urlopen(url,timeout=4).status==200 else 1)"

# uvicorn serves rag_engine.api:app on $PORT (PaaS sets PORT)
CMD ["sh", "-c", "uvicorn rag_engine.api:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
