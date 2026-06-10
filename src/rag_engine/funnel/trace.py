"""FunnelTrace — record the stage-by-stage candidate-set collapse for one query.

The hero narrative (spec §3.2): a query touches a PB-scale estate but only a
handful of rows reach the model. The funnel makes that reduction EXPLICIT and
checkable:

    PB raw  --tier/dedupe-->  TB indexable  --embed-->  GB vectors
            --structured pre-filter-->  ~thousands  --ANN coarse-->  ~hundreds
            --rerank-->  final_top_k

Real counts/bytes for the indexable path; the PB tail (BigQuery / Common Crawl)
carries a STATED scale (count may be None) + provenance from the catalog. The
trace asserts the candidate counts are monotonic non-increasing — the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FunnelStage:
    name: str
    count: int | None          # candidate count (None for the un-counted PB tail)
    bytes: int | None = None   # bytes at this stage (stated/real)
    note: str = ""             # e.g. "PB (stated, BigQuery)" / provenance link
    provenance_url: str = ""


class FunnelTrace:
    def __init__(self) -> None:
        self.stages: list[FunnelStage] = []

    def stage(self, name: str, count: int | None, bytes: int | None = None,
              note: str = "", provenance_url: str = "") -> "FunnelTrace":
        # enforce monotonic non-increasing on the COUNTED stages as they are added
        prev = self._last_count()
        if count is not None and prev is not None and count > prev:
            raise ValueError(
                f"funnel stage {name!r} count {count} > previous {prev} "
                f"(the funnel must only reduce)"
            )
        self.stages.append(FunnelStage(name=name, count=count, bytes=bytes,
                                       note=note, provenance_url=provenance_url))
        return self

    def _last_count(self) -> int | None:
        for s in reversed(self.stages):
            if s.count is not None:
                return s.count
        return None

    @property
    def counted(self) -> list[int]:
        return [s.count for s in self.stages if s.count is not None]

    def is_monotonic_non_increasing(self) -> bool:
        c = self.counted
        return all(b <= a for a, b in zip(c, c[1:]))

    def reduction_factor(self) -> float:
        c = self.counted
        if len(c) < 2 or c[-1] == 0:
            return float(c[0]) if c else 0.0
        return c[0] / c[-1]

    def to_rows(self) -> list[dict]:
        return [{"stage": s.name, "count": s.count, "bytes": s.bytes,
                 "note": s.note, "provenance_url": s.provenance_url} for s in self.stages]


def compute_funnel(catalog, candidate_counts: dict[str, int],
                   pb_tail_asset_ids: tuple[str, ...] = ()) -> FunnelTrace:
    """Build a funnel from a real candidate collapse + catalog PB-tail scale.

    ``candidate_counts`` maps the indexable-path stage names to their real counts
    (e.g. {"indexable_derivative": 50000, "structured_prefilter": 4000,
    "coarse_ann": 200, "rerank": 8, "final_top_k": 5}). ``pb_tail_asset_ids`` are
    catalog assets whose STATED scale (scale_badge/provenance) heads the funnel.
    """
    t = FunnelTrace()
    # PB tail — stated scale + provenance from the catalog (count un-counted)
    for aid in pb_tail_asset_ids:
        a = catalog.get(aid)
        t.stage(f"pb_tail:{aid}", count=None, note=a.scale_badge,
                provenance_url=a.provenance_url)
    # indexable path — real counts, in funnel order
    order = ["indexable_derivative", "structured_prefilter", "coarse_ann",
             "rerank", "final_top_k"]
    for name in order:
        if name in candidate_counts:
            t.stage(name, count=candidate_counts[name])
    return t
