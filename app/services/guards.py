from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ResourceNotFoundError


async def require_session(db: AsyncSession, session_id: UUID | None):
    if session_id is None:
        return None
    from app.repositories.sessions import get_session

    session = await get_session(db, session_id)
    if session is None:
        raise ResourceNotFoundError('Session not found')
    return session


def validate_document_scope(documents, requested_ids: list[UUID], session_id: UUID | None):
    document_map = {document.id: document for document in documents}
    missing = [document_id for document_id in requested_ids if document_id not in document_map]
    if missing:
        raise ResourceNotFoundError(f'Document not found: {missing[0]}')

    if session_id is not None:
        for document_id in requested_ids:
            if document_map[document_id].session_id != session_id:
                raise ResourceNotFoundError(
                    f'Document {document_id} is not available in this session'
                )
    return [document_map[document_id] for document_id in requested_ids]


async def require_document_scope(
    db: AsyncSession,
    document_ids: list[UUID],
    session_id: UUID | None,
):
    from app.repositories.documents import get_documents

    documents = await get_documents(db, document_ids)
    return validate_document_scope(documents, document_ids, session_id)
