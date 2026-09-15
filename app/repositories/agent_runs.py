from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_run import AgentRun


async def create_run(db: AsyncSession, **kwargs) -> AgentRun:
    item = AgentRun(**kwargs)
    db.add(item)
    await db.flush()
    return item
