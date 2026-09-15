from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_gemini_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.documents import get_document
from app.schemas.document import DocumentRead
from app.services.document_ingestion import ALLOWED_MIME, ingest_document
from app.services.gemini import GeminiService
from app.services.guards import require_session

router = APIRouter(prefix='/documents', tags=['documents'])


@router.post('/upload', response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    session_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(get_gemini_api_key),
):
    settings = get_settings()
    await require_session(db, session_id)

    mime_type = file.content_type or 'application/octet-stream'
    if mime_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail='Only PDF and TXT files are supported in version 1.')

    payload = await file.read()
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f'File exceeds {settings.max_upload_mb} MB limit',
        )

    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or 'upload').name
    path = Path(settings.upload_dir) / f'{uuid4()}_{safe_name}'
    path.write_bytes(payload)

    try:
        return await ingest_document(
            db,
            GeminiService(api_key),
            safe_name,
            mime_type,
            str(path),
            session_id,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get('/{document_id}', response_model=DocumentRead)
async def read_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    item = await get_document(db, document_id)
    if not item:
        raise HTTPException(status_code=404, detail='Document not found')
    return item
