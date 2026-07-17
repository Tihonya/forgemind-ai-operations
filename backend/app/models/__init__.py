"""ORM models package.

Re-exports the domain models so they are registered with Base.metadata
for Alembic autogenerate discovery.
"""

from app.models.diagnostic import DiagnosticJob

__all__ = ["DiagnosticJob"]
