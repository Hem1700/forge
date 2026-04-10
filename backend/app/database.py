from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


@event.listens_for(Base, "init", propagate=True)
def _apply_column_defaults(target, args, kwargs):
    """Apply column defaults to Python objects at construction time.

    SQLAlchemy's mapped_column(default=...) only fires at INSERT time.
    This listener ensures defaults are also set when constructing objects
    in-memory, which is essential for tests and business logic that
    inspects attributes before a flush.
    """
    mapper = sa_inspect(target.__class__)
    for attr in mapper.column_attrs:
        if attr.key not in kwargs:
            col = attr.columns[0]
            if col.default is not None:
                if col.default.is_callable:
                    kwargs[attr.key] = col.default.arg(None)
                elif col.default.is_scalar:
                    kwargs[attr.key] = col.default.arg


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
