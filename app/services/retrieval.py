from uuid import UUID
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services.rrf import reciprocal_rank_fusion


async def hybrid_retrieve(db: AsyncSession, query: str, query_embedding: list[float], document_ids: list[UUID], top_k: int):
    settings = get_settings()
    candidate_k = max(top_k * 3, 10)

    dense_stmt = (
        select(DocumentChunk, Document, DocumentChunk.embedding.cosine_distance(query_embedding).label('distance'))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(document_ids))
        .order_by('distance')
        .limit(candidate_k)
    )
    dense_rows = list((await db.execute(dense_stmt)).all())

    rank_expr = func.ts_rank_cd(DocumentChunk.content_tsv, func.websearch_to_tsquery('english', query))
    sparse_stmt = (
        select(DocumentChunk, Document, rank_expr.label('rank'))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(document_ids))
        .where(DocumentChunk.content_tsv.op('@@')(func.websearch_to_tsquery('english', query)))
        .order_by(desc('rank'))
        .limit(candidate_k)
    )
    sparse_rows = list((await db.execute(sparse_stmt)).all())

    dense_ids = [str(row[0].id) for row in dense_rows]
    sparse_ids = [str(row[0].id) for row in sparse_rows]
    fused = reciprocal_rank_fusion([dense_ids, sparse_ids], k=settings.rrf_k)
    score_map = dict(fused)

    row_map = {}
    for row in dense_rows + sparse_rows:
        chunk, document = row[0], row[1]
        row_map[str(chunk.id)] = (chunk, document)

    output = []
    for chunk_id, score in fused[:top_k]:
        chunk, document = row_map[chunk_id]
        output.append({'chunk': chunk, 'document': document, 'score': score})
    return output
