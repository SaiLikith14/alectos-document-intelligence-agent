from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_gemini_api_key
from app.db.session import get_db
from app.schemas.agent import AgentAnswer, AgentQuery
from app.services.document_agent import answer_question, stream_question
from app.services.gemini import GeminiService

router = APIRouter(prefix='/agents/document-intelligence', tags=['agents'])


@router.post('/query', response_model=AgentAnswer)
async def query(
    payload: AgentQuery,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_gemini_api_key),
):
    return await answer_question(db, GeminiService(api_key), payload)


@router.post('/query/stream')
async def query_stream(
    payload: AgentQuery,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_gemini_api_key),
):
    events = await stream_question(db, GeminiService(api_key), payload)
    return StreamingResponse(
        events,
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
