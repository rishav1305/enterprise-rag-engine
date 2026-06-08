"""Real public-source fixtures — queried IN PLACE, never bulk-loaded.

Each module exposes ``fixture(manifest) -> SourceOutput`` returning connection
metadata + provenance + scale badge + a ``sample_pull`` callable. The sample
callable is mocked in CI (no network); live pulls run only under the ``live``
pytest marker to protect BigQuery sandbox quota (cost guard, SECURE pillar).
Common Crawl is catalog-only — it has no sample pull at all.
"""
