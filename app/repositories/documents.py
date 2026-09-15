from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk


async def create_document(db: AsyncSession, **kwargs) -> Document:
    item = Document(**kwargs)
    db.add(item)
    await db.flush()
    return item


async def get_document(db: AsyncSession, document_id: UUID) -> Document | None:
    return await db.get(Document, document_id)


async def get_documents(db: AsyncSession, document_ids: list[UUID]) -> list[Document]:
    result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
    return list(result.scalars().all())


async def add_chunk(db: AsyncSession, **kwargs) -> DocumentChunk:
    item = DocumentChunk(**kwargs)
    db.add(item)
    await db.flush()
    return item


async def get_chunks_for_documents(db: AsyncSession, document_ids: list[UUID]) -> list[DocumentChunk]:
    result = await db.execute(select(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)))
    return list(result.scalars().all())
