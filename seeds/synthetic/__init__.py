"""Synthetic Meridian sources (16). Each module exposes ``generate(manifest, scale)``.

All synthetic data is clearly labeled (``synthetic=True`` in the manifest),
deterministically seeded, and coherent with the shared anchors in
``seeds._coherence``. PII is realistic-but-fake (Faker) and always maskable at
the governance layer for unauthorized roles — never simply absent.
"""
