"""External-source connectors (BigQuery PB tail, …) — query-in-place (P0.3a)."""

from .bigquery import BigQueryClient, FakeBigQueryClient, GuardedBigQuery

__all__ = ["BigQueryClient", "FakeBigQueryClient", "GuardedBigQuery"]
