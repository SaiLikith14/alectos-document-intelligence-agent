from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.repositories.sessions import create_session, get_session
from app.schemas.session import SessionCreate, SessionRead

router = APIRouter(prefix='/sessions', tags=['sessions'])


@router.post('', response_model=SessionRead, status_code=201)
async def create(payload: SessionCreate, db: AsyncSession = Depends(get_db)):
    return await create_session(db, payload.title)


@router.get('/{session_id}', response_model=SessionRead)
async def read(session_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await get_session(db, session_id)
    if not item:
        raise HTTPException(status_code=404, detail='Session not found')
    return item
