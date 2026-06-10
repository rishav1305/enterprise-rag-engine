"""P0.3a — live BigQuery confirmation (creds-gated, NOT part of the CI gate).

Marked ``bq`` + skipif on GOOGLE_APPLICATION_CREDENTIALS + BQ_PROJECT. Runs only
with `pytest -m bq` when GCP sandbox creds are in env; CI runs
`-m "not cloud and not bq"`. Proves the SAME GuardedBigQuery 4-gate contract
against a real client: an unpruned NYC TLC query is REFUSED; a pruned aggregate
under the cap returns. Read-only creds; no secrets committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

_HAVE_CREDS = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.getenv("BQ_PROJECT"))


@pytest.mark.bq
@pytest.mark.skipif(not _HAVE_CREDS,
                    reason="no GCP creds (set GOOGLE_APPLICATION_CREDENTIALS + BQ_PROJECT)")
def test_live_bigquery_cost_guard():
    pytest.importorskip("google.cloud.bigquery")
    from google.cloud import bigquery

    from rag_engine.config import EngineConfig
    from rag_engine.connectors.bigquery import GuardedBigQuery
    from rag_engine.sql.cost_guard import CostGuardError

    cfg = EngineConfig()
    bq = bigquery.Client(project=os.environ["BQ_PROJECT"])

    class _RealClient:
        def dry_run_bytes_for(self, sql: str) -> int:
            job = bq.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True,
                                                                   use_query_cache=False))
            return int(job.total_bytes_processed)

        def execute(self, sql: str, max_bytes_billed: int):
            cfg_ = bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes_billed)
            return list(bq.query(sql, job_config=cfg_).result())

    part = "pickup_datetime"
    ds = "bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2018"
    g = GuardedBigQuery.from_config(_RealClient(), part, cfg)

    # unpruned -> REFUSED before any bytes are billed
    with pytest.raises(CostGuardError):
        g.run(f"SELECT * FROM `{ds}`")

    # pruned aggregate under the cap -> returns
    rows = g.run(
        f"SELECT COUNT(*) AS n FROM `{ds}` "
        f"WHERE {part} >= '2018-01-01' AND {part} < '2018-01-02'"
    )
    assert rows
