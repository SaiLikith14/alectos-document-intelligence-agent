from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.session import Session


async def create_session(db: AsyncSession, title: str | None = None) -> Session:
    item = Session(title=title)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_session(db: AsyncSession, session_id: UUID) -> Session | None:
    return await db.get(Session, session_id)
