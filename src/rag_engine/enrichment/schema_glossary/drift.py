"""Schema-drift detection over the glossary (P0.4).

A governed glossary goes stale when the warehouse schema changes. Drift =
  * NEW physical columns present in the live schema but absent from the glossary
    (their meaning is unknown -> must be drafted/approved), and
  * VANISHED glossary entries whose physical column no longer exists (a renamed or
    dropped column -> the stale description could mislead text-to-SQL).

A CI test asserts ``detect_drift`` is empty against the current schema, so a schema
change that isn't reflected in the glossary fails the build.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .glossary import Glossary


@dataclass(frozen=True)
class GlossaryDrift:
    new_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    vanished_entries: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return not self.new_columns and not self.vanished_entries


def detect_drift(
    glossary: Glossary,
    current_columns: Iterable[tuple[str, str]],
) -> GlossaryDrift:
    """Compare the glossary's (table, physical) keys to the live schema's columns."""
    live = {(t, c) for t, c in current_columns}
    known = {e.key for e in glossary.all()}
    new = tuple(sorted(live - known))          # in schema, not in glossary
    vanished = tuple(sorted(known - live))     # in glossary, gone from schema
    return GlossaryDrift(new_columns=new, vanished_entries=vanished)
