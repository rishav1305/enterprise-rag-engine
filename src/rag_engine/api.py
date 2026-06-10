"""FastAPI surface for the governed RAG engine.

The caller's identity comes from headers (in production: a validated JWT /
OIDC token). We deliberately derive the :class:`Session` server-side and never
trust a role passed in the request body, so a client cannot self-escalate.

Run::

    uvicorn rag_engine.api:app --reload
    curl -s localhost:8000/query \
      -H 'X-User-Id: intern-1' -H 'X-User-Roles: INTERN' -H 'X-Clearance: 1' \
      -H 'content-type: application/json' \
      -d '{"question":"What is the remote work policy?"}' | jq
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import EngineConfig
from .deploy.guards import RateLimiter, RateLimitExceeded, assert_synthetic_only
from .pipeline import RAGPipeline
from .schemas import RAGResponse, Session

_CORPUS = Path(os.getenv("RAG_CORPUS_DIR", Path(__file__).resolve().parents[2] / "corpus"))

_state: dict[str, object] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = EngineConfig()
    # GATE B: refuse to start if the synthetic demo profile can reach a real source.
    assert_synthetic_only(cfg)
    pipeline = RAGPipeline(config=cfg)
    count = pipeline.index_corpus(_CORPUS)
    app.state.indexed_chunks = count
    _state["pipeline"] = pipeline
    # GATE B: per-key abuse cap (rate-limit + per-day) BEFORE any LLM/embedding call.
    _state["rate_limiter"] = RateLimiter(cfg.rate_limit_per_min, cfg.query_cap_per_day)
    yield
    _state.clear()


app = FastAPI(title="Adaptive Enterprise RAG", version="0.1.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indexed_chunks": app.state.indexed_chunks}


@app.post("/query", response_model=RAGResponse)
def query(
    req: QueryRequest,
    x_user_id: str = Header(default="anonymous"),
    x_user_roles: str = Header(default="PUBLIC"),
    x_clearance: int = Header(default=0),
) -> RAGResponse:
    # GATE B: abuse cap keyed by user id, BEFORE the (potentially live) LLM/embedding
    # call. A public URL backed by live keys would otherwise let anyone run up bills.
    limiter = _state.get("rate_limiter")
    if limiter is not None:
        try:
            limiter.check(x_user_id)
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=e.reason) from e

    session = Session(
        user_id=x_user_id,
        roles=[r.strip() for r in x_user_roles.split(",") if r.strip()],
        clearance_level=int(x_clearance),
    )
    return _state["pipeline"].query(req.question, session)
