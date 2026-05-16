"""Importing this package registers every ORM model with Base.metadata.

SQLAlchemy resolves foreign keys by table name at compile time. If a
process imports `Engagement` (which has an FK to `organizations`) but
never imports `Organization`, the FK target table is missing from the
metadata and pipeline writes fail at runtime with "could not find
table 'organizations'".

Listing every model here once means any `from app.models.<x> import ...`
also triggers this file, which in turn loads all model classes.
"""
from app.models import (  # noqa: F401
    agent,
    api_key,
    engagement,
    engagement_event,
    finding,
    knowledge,
    organization,
    task,
    user,
)
