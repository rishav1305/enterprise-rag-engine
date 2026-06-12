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
from pydantic import BaseModel, Field

from .config import EngineConfig
from .deploy.guards import RateLimiter, RateLimitExceeded, assert_synthetic_only
from .pipeline import RAGPipeline
from .schemas import RAGResponse, Session

_CORPUS = Path(os.getenv("RAG_CORPUS_DIR", Path(__file__).resolve().parents[2] / "corpus"))

_state: dict[str, object] = {}


def _demo_catalog():
    """A small synthetic CatalogRegistry so the /funnel viz shows real PB->TB->GB
    scale (the corpus-only wiring leaves catalog=None -> empty funnel). These are
    SYNTHETIC assets with stated scale badges — no real data, no row content."""
    from .catalog.asset import CatalogAsset
    from .catalog.registry import CatalogRegistry
    from .schemas import SecurityContext

    reg = CatalogRegistry()
    # (asset_id, vertical, class, level, badge, allowed/ntk roles)
    demo_assets = [
        ("nyc_tlc_trips", "TRANSPORT", "A", 0, "≈1.6B rows · ~400 GB", []),
        ("gdelt_events", "NEWS", "A", 0, "≈800M events · ~250 GB", []),
        ("meridian_warehouse", "FINANCE", "C", 2, "≈40M rows · ~12 GB", []),
        # G0: the governing assets for the two new corpus docs (so RAGPipeline.asset_for
        # resolves them by parent_doc_id; the trace surfaces the governing asset).
        ("customer-account-sample", "CUSTOMER_SUPPORT", "D", 3,
         "1 sample record (class-D customer PII)", []),
        ("dept-scoped-record", "ENGINEERING", "G", 2,
         "1 sample record (dept-scoped, partial)", ["ENGINEERING"]),
    ]
    for aid, vert, cls, lvl, badge, ntk in demo_assets:
        reg._assets[aid] = CatalogAsset(
            asset_id=aid, vertical=vert, retrieval_mode="structured",
            sensitivity_class=cls, scale_badge=badge,
            security=SecurityContext(allowed_roles=ntk, clearance_level=lvl,
                                     sensitivity_class=cls, need_to_know_roles=ntk),
        )
    return reg


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = EngineConfig()
    # GATE B: refuse to start if the synthetic demo profile can reach a real source.
    assert_synthetic_only(cfg)
    pipeline = RAGPipeline(config=cfg, catalog=_demo_catalog())
    count = pipeline.index_corpus(_CORPUS)
    app.state.indexed_chunks = count
    _state["pipeline"] = pipeline
    _state["config"] = cfg   # G1: per-request synthetic-profile check on /trace
    # GATE B: per-key abuse cap (rate-limit + per-day) BEFORE any LLM/embedding call.
    _state["rate_limiter"] = RateLimiter(
        cfg.rate_limit_per_min, cfg.query_cap_per_day,
        instance_per_min=cfg.instance_rate_limit_per_min)
    yield
    _state.clear()


app = FastAPI(title="Adaptive Enterprise RAG", version="0.1.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


class Citation(BaseModel):
    """A client-facing citation — only the ADMITTED (governed) sources."""

    parent_doc_id: str
    parent_title: str
    quote: str


class ClientRAGResponse(BaseModel):
    """The CLIENT-facing response. CRITICAL (P0.11b FIX): the full ``governance_trail``
    (denied-doc ids, required_roles, required-clearance reasons) is OPERATOR-ONLY — it
    goes to the audit sink, NEVER to the HTTP requester. A denied caller learns only
    that some items were withheld (a COUNT), never WHAT exists or what unlocks it.
    """

    query: str
    answer: str
    architecture: str
    citations: list[Citation] = Field(default_factory=list)
    access_denied: bool = False
    admitted: int = 0
    n_withheld: int = 0   # COUNT only — never the ids/ACLs of withheld content


def _to_client_response(resp: "RAGResponse") -> ClientRAGResponse:
    """Strip the operator-only trail/ACL metadata at the API boundary. The full
    RAGResponse (incl. governance_trail) stays internal for audit; the client sees a
    redacted view: governed citations + a withheld COUNT, no ACL details, no denied ids.
    """
    # withheld = anything the governance trail did not fully ALLOW (deny + mask +
    # partial). COUNT only — the client never learns WHICH items or their ACLs. Use the
    # explicit resp.n_withheld (authoritative + STABLE across cache hits, where the
    # trail is intentionally empty); fall back to the trail for older callers.
    n_withheld = resp.n_withheld or sum(
        1 for d in resp.governance_trail if d.decision != "allow")
    return ClientRAGResponse(
        query=resp.query,
        answer=resp.answer,
        architecture=str(getattr(resp.architecture, "value", resp.architecture)),
        citations=[Citation(parent_doc_id=c.parent_doc_id,
                            parent_title=c.parent_title, quote=c.quote)
                   for c in resp.citations],
        access_denied=resp.access_denied,
        admitted=resp.admitted,
        n_withheld=n_withheld,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indexed_chunks": app.state.indexed_chunks}


@app.get("/personas")
def personas() -> dict:
    """B2 — read-only switcher metadata: persona title/roles/clearance ONLY (no
    content). The UI uses this to populate the persona dropdown; the actual governance
    happens server-side from the headers, never from this list.

    Sourced from the runtime-safe ``demo_data`` (the lean prod container does NOT install
    the seed-generation deps); falls back to the seed package when available (dev)."""
    from .demo_data import DEMO_PERSONAS

    try:
        from seeds.emit import build_oracle
        p = build_oracle()["personas"]
        return {"personas": [
            {"key": k, "title": v["title"], "roles": list(v["roles"]),
             "clearance": v["level"]}
            for k, v in p.items()
        ]}
    except Exception:
        return {"personas": DEMO_PERSONAS}


@app.get("/glossary")
def glossary() -> dict:
    """B4 — read-only opaque-schema mapping (text_2 -> "customer name"). Exposes ONLY
    the schema mapping (table/physical/meaning/confidence) — NO row data, NO example
    values (which could carry real-shaped data)."""
    from .demo_data import DEMO_GLOSSARY, DEMO_LEGACY_VIEWS

    # Prefer LIVE mining (dev, with sqlglot) so the demo reflects the real miner; fall
    # back to the baked deterministic mapping in the lean prod container (no sqlglot).
    try:
        from .enrichment.schema_glossary.view_miner import mine_views
        mined = mine_views(DEMO_LEGACY_VIEWS)
        entries = [{"table": t, "physical": p, "means": m, "confidence": "high"}
                   for (t, p), m in sorted(mined.items())]
    except Exception:
        entries = list(DEMO_GLOSSARY)
    return {"glossary": entries}   # mapping only — NO row data / example values


@app.get("/funnel")
def funnel() -> dict:
    """B5 — read-only PB->TB->GB scale viz. Stated scale numbers + the stage collapse
    only — no row content."""
    pipe = _state["pipeline"]
    catalog = getattr(pipe, "catalog", None)
    stages = []
    if catalog is not None:
        try:
            from .funnel.trace import compute_funnel
            # PB-tail head = the catalog's stated-scale assets; the indexable path uses
            # the demo's representative collapse counts (PB stated -> GB indexable ->
            # the top-k that actually reaches the model).
            pb_ids = tuple(a.asset_id for a in catalog.all())
            counts = {"indexable_derivative": 50_000, "structured_prefilter": 4_000,
                      "coarse_ann": 200, "rerank": 8, "final_top_k": 5}
            t = compute_funnel(catalog, candidate_counts=counts,
                               pb_tail_asset_ids=pb_ids)
            stages = t.to_rows()
        except Exception:
            stages = []
    return {"funnel": stages}


@app.post("/query", response_model=ClientRAGResponse)
def query(
    req: QueryRequest,
    x_user_id: str = Header(default="anonymous"),
    x_user_roles: str = Header(default="PUBLIC"),
    x_clearance: int = Header(default=0),
) -> ClientRAGResponse:
    # GATE B: abuse cap keyed by user id, BEFORE the (potentially live) LLM/embedding
    # call. A public URL backed by live keys would otherwise let anyone run up bills.
    limiter = _state.get("rate_limiter")
    if limiter is not None:
        try:
            limiter.check(x_user_id)
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=e.reason) from e

    # ROBUST: clamp the header clearance to the valid [0,5] range so a malformed value
    # (99/-3) is a clean 4xx, never a 500 panic. (Non-int already 422s at parse time.)
    try:
        clearance = int(x_clearance)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail="X-Clearance must be an integer") from e
    if not (0 <= clearance <= 5):
        raise HTTPException(status_code=422, detail="X-Clearance must be in [0,5]")

    session = Session(
        user_id=x_user_id,
        roles=[r.strip() for r in x_user_roles.split(",") if r.strip()],
        clearance_level=clearance,
    )
    # the pipeline audits the FULL governance_trail server-side (self.audit.record);
    # the client gets the REDACTED view (no trail/ACL details, withheld COUNT only).
    full = _state["pipeline"].query(req.question, session)
    return _to_client_response(full)


# ---- G1: the glass-box /trace endpoints ----------------------------------
class TraceRequest(BaseModel):
    question: str


def _require_synthetic() -> None:
    """G1: /trace is SYNTHETIC-ONLY — a trace surfaces governance internals, so it must
    NEVER run against a real-data profile (no real PII can enter a trace). The startup
    guard already refused a live source; this is the per-request backstop."""
    cfg = _state.get("config")
    if cfg is not None and getattr(cfg, "demo_profile", "synthetic") != "synthetic":
        raise HTTPException(status_code=403,
                            detail="/trace is available only under the synthetic demo profile")


def _guarded_session(x_user_id, x_user_roles, x_clearance) -> Session:
    """Shared: rate-limit + clearance clamp + build the Session (mirrors /query)."""
    limiter = _state.get("rate_limiter")
    if limiter is not None:
        try:
            limiter.check(x_user_id)
        except RateLimitExceeded as e:
            raise HTTPException(status_code=429, detail=e.reason) from e
    try:
        clearance = int(x_clearance)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail="X-Clearance must be an integer") from e
    if not (0 <= clearance <= 5):
        raise HTTPException(status_code=422, detail="X-Clearance must be in [0,5]")
    return Session(
        user_id=x_user_id,
        roles=[r.strip() for r in x_user_roles.split(",") if r.strip()],
        clearance_level=clearance,
    )


@app.post("/trace")
def trace(
    req: TraceRequest,
    x_user_id: str = Header(default="anonymous"),
    x_user_roles: str = Header(default="PUBLIC"),
    x_clearance: int = Header(default=0),
) -> dict:
    """The glass-box trace: the engine's REAL per-query trace (governance parity with
    access.evaluate). Synthetic-only, rate-limited, clearance-clamped. /query is
    unchanged (this is additive)."""
    _require_synthetic()
    session = _guarded_session(x_user_id, x_user_roles, x_clearance)
    from .trace import build_trace

    cfg = _state.get("config")
    return build_trace(req.question, session, config=cfg).model_dump()


@app.get("/trace/catalog")
def trace_catalog() -> dict:
    """The full estate (23 sources) for the Datasets tab. Synthetic-only; read-only
    metadata (name/type/scale/class/clearance/provenance/live_queryable) — no row data."""
    _require_synthetic()
    from .catalog.estate import build_estate
    return build_estate()
