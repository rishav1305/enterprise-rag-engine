"""The funnel — PB->TB->GB->candidates reduction, made explicit (spec §3.2)."""

from .trace import FunnelStage, FunnelTrace, compute_funnel

__all__ = ["FunnelStage", "FunnelTrace", "compute_funnel"]
