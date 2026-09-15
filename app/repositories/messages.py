from sqlalchemy.ext.asyncio import AsyncSession
from app.models.message import Message


async def add_message(db: AsyncSession, **kwargs) -> Message:
    item = Message(**kwargs)
    db.add(item)
    await db.flush()
    return item
