# 11 — The demo API + Gate A / Gate B deploy-security

The demo makes the headline legible — and because the deploy turns every "latent, not
user-reachable" finding into a **live** one, two non-negotiable gates govern it.

## The FastAPI surface (`api.py`)

The caller's identity is derived **server-side** from headers (`X-User-Id` / `X-User-Roles` /
`X-Clearance`) — the demo trust model is "**headers ARE the entitlement**". A role/clearance in the
request **body is ignored** (no self-escalation;
`tests/test_api_http_governance.py::test_body_role_is_ignored_no_self_escalation` proves it over
HTTP).

| Endpoint | Purpose | Gate A coverage |
|---|---|---|
| `POST /query` | the persona switcher (same query, different governed answers) | HTTP e2e leak test + self-escalation test |
| `GET /personas` | switcher options (title/roles/clearance only) | read-only; no restricted content |
| `GET /glossary` | `text_2 → meaning` mapping | read-only; mapping only, no row data |
| `GET /funnel` | PB→TB→GB scale viz | read-only; stated scale only |
| `GET /health` | liveness | n/a |

`POST /warehouse` is **NOT exposed** — the warehouse SQL path is pipeline-proven but gets no HTTP
endpoint, minimizing the public attack surface.

### The client response is redacted (the trail-disclosure fix)

`/query` returns a `ClientRAGResponse` — `answer` + governed `citations` + a withheld **COUNT**
(`n_withheld`), and nothing else. The full `governance_trail` (denied-doc ids, `required_roles`,
required-clearance reasons) is **operator-only** — it goes to the audit sink server-side, never to
the HTTP requester. A denied caller learns only that *some* items were withheld, never **what
exists or what unlocks it**. The leak oracle scans the **whole** serialized response for ACL markers
(`tests/test_api_http_governance.py`).

`X-Clearance` out of range → a clean **422** (not a 500 panic); ROBUST.

## 🔴 GATE A — entry-point leak coverage (per-HTTP-endpoint)

Every backend entry point the demo UI exposes has a passing **end-to-end leak test against the
actual HTTP call path** (FastAPI `TestClient`, including the header→Session derivation — not
`pipeline.query()`). Classification: routes through `/query` (proven) · a new endpoint ships **with**
its own biting e2e leak test, or it does not ship · read-only metadata (still enumerated). No
endpoint reaches the UI without its own leak test that bites.

## 🔴 GATE B — operational deploy-security (`deploy/guards.py`)

These sit **outside the leak oracle** (the review net can't catch them):

- **Rate-limit + per-day cap** — `RateLimiter` enforces a **per-key** sliding-window rate-limit +
  per-day cap AND an **instance-wide** cap (closes the `X-User-Id`-rotation bypass of the per-key
  cap), BEFORE any LLM/embedding call → HTTP 429. (Front the public URL with **Cloudflare** edge
  rate-limiting too.)
- **Synthetic-data-only refuse-to-start** — `assert_synthetic_only(config)` refuses to start the
  app under `demo_profile=synthetic` if a non-synthetic source is reachable (live SurrealDB Cloud
  DSN, GROQ/RAG_SQL/VOYAGE/ANTHROPIC creds, openai grader, groq/nvidia sql_generator). A leak in
  synthetic data is theater; against real data it is not.
- **Server-side-only secrets** — ALL LLM/DB/embedding creds live in the FastAPI server. The
  frontend (`portfolio_app/src/app/projects/clearance`) reaches the backend via a Next.js
  **route-handler proxy** (`/api/clearance/query` + `/meta`) so the backend URL lives in a
  server-side `CLEARANCE_API_URL` env var (**never `NEXT_PUBLIC_*`**) — not in the client bundle.
  A build-step **client-bundle no-secrets scan** (`portfolio_app/scripts/scan-client-bundle.mjs`,
  `npm run scan:bundle`) scans `.next/static` after `next build` for secret-shaped strings + any
  `NEXT_PUBLIC_*` credential var, and **fails the build** on a violation (mutation-proven: a planted
  `sk-` secret → exit 1).

All three are mutation-proven and **hard-block public go-live** (deep dive [§12](12-ops-runbook.md)).

## The frontend (pure client of the governed API)

The FE displays exactly what the (already-governed, already-redacted) API returns — **no
client-side governance** (nothing bypassable via the network tab; the API is the only gate).
Answers are rendered as **plain text** (no `dangerouslySetInnerHTML` — XSS-safe). The persona
switcher shows the same query as Intern/Data-Analyst/Finance/CFO side by side; `n_withheld` is the
governance signal.
