"""The 7 real public-source fixtures (world bible §6), queried in place.

Each ``fixture(manifest)`` registers catalog metadata + connection config +
provenance + scale badge. No bulk loads; sample pulls are mocked in CI.
Connection config carries no credentials (env-injected at serve time).
"""

from __future__ import annotations

from .._base import SourceOutput
from ..manifest import FieldSpec, Manifest
from ._fixture import RealSourceSpec, build_fixture

# --- TPC-DS store_sales (BigQuery) ----------------------------------------
def tpcds(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="tpcds_store_sales",
        in_story_name="Marketplace transactions",
        source="TPC-DS store_sales (BigQuery public)",
        provenance_url="https://www.tpc.org/tpcds/",
        scale_badge="up to 10 TB",
        connector="Warehouse (BigQuery)",
        vertical="COMMERCE",
        retrieval_mode="structured",
        sensitivity_class="C",  # raw L3 via field ACL; aggregates L1
        clearance_level=2,
        owner_department="COMMERCE",
        fields=(
            FieldSpec("ss_item_sk", "int"),
            FieldSpec("ss_customer_sk", "int"),
            FieldSpec("ss_sales_price", "float"),
            FieldSpec("customer_email", "str", pii=True, masked=True),
        ),
        connection={"engine": "bigquery", "dataset": "bigquery-public-data.tpcds_2t",
                    "partition_field": "ss_sold_date_sk", "requires_partition_filter": True},
    ))


# --- NYC TLC trips (BigQuery) ---------------------------------------------
def nyc_tlc(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="nyc_tlc_trips",
        in_story_name="Mobility trips",
        source="NYC TLC (BigQuery public)",
        provenance_url="https://console.cloud.google.com/marketplace/details/city-of-new-york/nyc-tlc-trips",
        scale_badge="≈1.6B rows · ~400 GB",
        connector="Data lake (BigQuery)",
        vertical="MOBILITY_OPS",
        retrieval_mode="structured",
        sensitivity_class="C",  # pickup/dropoff coords masked (PII); aggregates L1
        clearance_level=2,
        owner_department="MOBILITY_OPS",
        fields=(
            FieldSpec("pickup_datetime", "timestamp"),
            FieldSpec("fare_amount", "float"),
            FieldSpec("pickup_longitude", "float", pii=True, masked=True),
            FieldSpec("pickup_latitude", "float", pii=True, masked=True),
        ),
        connection={"engine": "bigquery",
                    "dataset": "bigquery-public-data.new_york_taxi_trips",
                    "partition_field": "pickup_datetime", "requires_partition_filter": True},
    ))


# --- GDELT events (BigQuery) ----------------------------------------------
def gdelt(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="gdelt_events",
        in_story_name="Global events / risk signals",
        source="GDELT (BigQuery public)",
        provenance_url="https://www.gdeltproject.org/",
        scale_badge="billions · 15-min cadence",
        connector="Data-share (BigQuery)",
        vertical="STRATEGY",
        retrieval_mode="structured",
        sensitivity_class="B",
        clearance_level=1,
        owner_department="STRATEGY",
        fields=(
            FieldSpec("GLOBALEVENTID", "int"),
            FieldSpec("SQLDATE", "int"),
            FieldSpec("Actor1Name", "str"),
            FieldSpec("AvgTone", "float"),
        ),
        connection={"engine": "bigquery", "dataset": "gdelt-bq.gdeltv2.events",
                    "partition_field": "SQLDATE", "requires_partition_filter": True},
    ))


# --- Common Crawl (S3) — CATALOG-ONLY (PB tail, never pulled) --------------
def common_crawl(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="common_crawl",
        in_story_name="Web / competitor corpus",
        source="Common Crawl (AWS S3)",
        provenance_url="https://commoncrawl.org/",
        scale_badge="PB-scale (catalog-only)",
        connector="S3 object store",
        vertical="STRATEGY",
        retrieval_mode="funnel",
        sensitivity_class="B",
        clearance_level=1,
        owner_department="STRATEGY",
        fields=(FieldSpec("warc_path", "str"), FieldSpec("url", "str")),
        connection={"engine": "s3", "bucket": "commoncrawl", "region": "us-east-1",
                    "note": "query in place, sample only; never bulk-download (egress guard)"},
        catalog_only=True,
    ))


# --- SEC EDGAR (API) ------------------------------------------------------
def sec_edgar(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="sec_edgar",
        in_story_name="Company filings (due diligence)",
        source="SEC EDGAR",
        provenance_url="https://www.sec.gov/edgar",
        scale_badge="≈16M filings",
        connector="Files / API",
        vertical="STRATEGY",
        retrieval_mode="vector",
        sensitivity_class="A",  # public L0
        clearance_level=0,
        owner_department="STRATEGY",
        fields=(FieldSpec("cik", "str"), FieldSpec("form_type", "str"),
                FieldSpec("filing_date", "str"), FieldSpec("text", "str")),
        connection={"engine": "http", "base_url_env": "EDGAR_BASE_URL",
                    "default_base_url": "https://data.sec.gov"},
    ))


# --- data.gov (API) -------------------------------------------------------
def data_gov(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="data_gov",
        in_story_name="Open city/economic data",
        source="data.gov",
        provenance_url="https://data.gov/",
        scale_badge="varies",
        connector="Files / API",
        vertical="MARKETING",
        retrieval_mode="structured",
        sensitivity_class="A",  # public L0
        clearance_level=0,
        owner_department="MARKETING",
        fields=(FieldSpec("dataset_id", "str"), FieldSpec("title", "str"),
                FieldSpec("value", "float")),
        connection={"engine": "http", "base_url_env": "DATAGOV_BASE_URL",
                    "default_base_url": "https://catalog.data.gov"},
    ))


# --- Wikipedia/Wikimedia (dump) — the VECTOR KB primary -------------------
def wikipedia(manifest: Manifest) -> SourceOutput:
    return build_fixture(manifest, RealSourceSpec(
        asset_id="wikipedia_kb",
        in_story_name="Internal knowledge base",
        source="Wikipedia/Wikimedia dump",
        provenance_url="https://dumps.wikimedia.org/",
        scale_badge="≈6.8M articles",
        connector="Confluence/wiki",
        vertical="KNOWLEDGE_SUPPORT",
        retrieval_mode="vector",
        sensitivity_class="B",  # L0-L1; the vector-KB derivative feeds TurboVec (P0.2b)
        clearance_level=1,
        owner_department="KNOWLEDGE_SUPPORT",
        fields=(FieldSpec("page_id", "str"), FieldSpec("title", "str"),
                FieldSpec("text", "str")),
        connection={"engine": "dump", "derivative": "vector_kb_sample",
                    "feeds": "turbovec_index (P0.2b)"},
    ))


FIXTURES = (tpcds, nyc_tlc, gdelt, common_crawl, sec_edgar, data_gov, wikipedia)
