from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.repositories.documents import add_chunk, create_document
from app.services.chunking import chunk_text
from app.services.gemini import GeminiService

ALLOWED_MIME = {'application/pdf', 'text/plain'}


def extract_pages(path: Path, mime_type: str) -> list[tuple[int | None, str]]:
    if mime_type == 'application/pdf':
        reader = PdfReader(str(path))
        return [(index + 1, page.extract_text() or '') for index, page in enumerate(reader.pages)]
    return [(None, path.read_text(encoding='utf-8', errors='ignore'))]


async def ingest_document(
    db: AsyncSession,
    gemini: GeminiService,
    filename: str,
    mime_type: str,
    storage_path: str,
    session_id: UUID | None,
):
    if mime_type not in ALLOWED_MIME:
        raise BadRequestError('Only PDF and TXT files are supported in version 1.')

    document = await create_document(
        db,
        filename=filename,
        mime_type=mime_type,
        storage_path=storage_path,
        session_id=session_id,
        status='processing',
    )

    try:
        pages = extract_pages(Path(storage_path), mime_type)
        chunk_records: list[tuple[int | None, str]] = []
        for page_number, page_text in pages:
            for chunk in chunk_text(page_text):
                chunk_records.append((page_number, chunk))

        if not chunk_records:
            raise BadRequestError('No readable text could be extracted from the document.')

        vectors = gemini.embed_texts([content for _, content in chunk_records])
        if len(vectors) != len(chunk_records):
            raise RuntimeError(
                f'Embedding count mismatch: {len(chunk_records)} chunks were created '
                f'but {len(vectors)} embeddings were returned.'
            )

        for index, ((page_number, content), vector) in enumerate(
            zip(chunk_records, vectors, strict=True)
        ):
            await add_chunk(
                db,
                document_id=document.id,
                chunk_index=index,
                page_number=page_number,
                content=content,
                embedding=vector,
            )

        await db.execute(
            sql_text(
                "UPDATE document_chunks "
                "SET content_tsv = to_tsvector('english', content) "
                "WHERE document_id = :document_id"
            ),
            {'document_id': document.id},
        )

        document.page_count = len(pages) if mime_type == 'application/pdf' else 1
        document.status = 'ready'
        document.error_message = None
        await db.commit()
        await db.refresh(document)
        return document
    except Exception:
        # create_document() and add_chunk() only flush until success, so rollback
        # removes the incomplete document and every chunk created in this request.
        await db.rollback()
        raise
