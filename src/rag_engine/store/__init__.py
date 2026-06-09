"""Store package — SurrealDB-backed unified store (P0.2a)."""

from .schema import ddl_statements
from .surreal import SurrealStore

__all__ = ["SurrealStore", "ddl_statements"]
