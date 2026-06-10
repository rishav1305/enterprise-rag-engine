#!/usr/bin/env bash
# GATE B pre-publish checklist against a LIVE backend URL. Go-live is gated on this
# passing — not a vibe. Usage: scripts/deploy-check.sh https://clearance-demo-api.fly.dev
set -uo pipefail

URL="${1:-}"
if [ -z "$URL" ]; then echo "usage: $0 <backend-base-url>"; exit 2; fi
URL="${URL%/}"
fail=0
ok()   { echo "  ✓ $1"; }
bad()  { echo "  ✗ $1"; fail=1; }

echo "== Gate B pre-publish checklist: $URL =="

# 1. liveness
code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")
[ "$code" = "200" ] && ok "/health 200 (backend reachable)" || bad "/health returned $code"

# 2. governed query works + a denied persona's response carries NO ACL trail
resp=$(curl -s -X POST "$URL/query" -H 'content-type: application/json' \
  -H 'X-User-Id: chk-intern' -H 'X-User-Roles: INTERN' -H 'X-Clearance: 1' \
  -d '{"question":"what is the executive compensation schedule"}')
echo "$resp" | grep -q '"n_withheld"' && ok "query returns the redacted ClientRAGResponse (n_withheld present)" \
  || bad "query response missing n_withheld (wrong response model?)"
# the denied intern's WHOLE response must carry no ACL metadata
if echo "$resp" | grep -qiE 'governance_trail|required_roles|required L5|hr-exec-comp|C_SUITE|HR_ADMIN'; then
  bad "ACL TRAIL DISCLOSED to a denied caller — go-live BLOCKED"
else
  ok "no ACL trail / required-roles / denied-doc-id in the denied-persona response"
fi

# 3. synthetic-only profile is active (the public introspection / health is up under it).
#    A live cred would have made the app refuse to start -> /health would be down. Since
#    /health is 200, assert_synthetic_only passed at startup. Double-check via the meta:
pj=$(curl -s "$URL/personas")  # GET, not rate-limited
echo "$pj" | grep -q '"personas"' && ok "metadata endpoints serve (synthetic profile booted)" \
  || bad "/personas not serving (startup may have refused — check for a live cred)"

# 4. clearance out-of-range -> clean 4xx (not 500)
c=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/query" -H 'content-type: application/json' \
    -H 'X-User-Id: chk-clr' -H 'X-User-Roles: PUBLIC' -H 'X-Clearance: 99' -d '{"question":"hi"}')
[ "$c" = "422" ] && ok "X-Clearance out-of-range -> 422 (ROBUST, no 500)" || bad "X-Clearance=99 returned $c (expected 422)"
# 5. rate-limit is live (LAST — it exhausts the per-key/instance budget): hammer past the per-min cap -> a 429 appears.
echo "  …probing rate-limit (expect a 429 within ~35 requests)…"
got429=0
for i in $(seq 1 35); do
  c=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/query" \
      -H 'content-type: application/json' -H 'X-User-Roles: PUBLIC' -H 'X-Clearance: 0' \
      -d '{"question":"hi"}')
  if [ "$c" = "429" ]; then got429=1; break; fi
done
[ "$got429" = "1" ] && ok "rate-limit returns 429 on abuse" || bad "no 429 after 35 requests — rate-limit not enforced"


echo
if [ "$fail" = "0" ]; then
  echo "✓ GATE B PASS — backend cleared for public go-live."
  echo "  (Also confirm separately: client-bundle scan clean + leak-oracle green in CI.)"
  exit 0
else
  echo "✗ GATE B FAIL — go-live BLOCKED. Fix the ✗ items above."
  exit 1
fi
