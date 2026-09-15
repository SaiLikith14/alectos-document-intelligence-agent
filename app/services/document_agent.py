import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AlectosError
from app.repositories.agent_runs import create_run
from app.repositories.messages import add_message
from app.schemas.agent import AgentAnswer, AgentRunInfo, Citation, RetrievalInfo
from app.services.gemini import GeminiService
from app.services.guards import require_document_scope, require_session
from app.services.retrieval import hybrid_retrieve
from app.services.streaming import sse_event


@dataclass
class PreparedAnswer:
    started: float
    run: object
    citations: list[Citation]
    context: str
    sources_used: int


async def _prepare_answer(
    db: AsyncSession,
    gemini: GeminiService,
    payload,
) -> PreparedAnswer:
    await require_session(db, payload.session_id)
    await require_document_scope(db, payload.document_ids, payload.session_id)

    started = time.perf_counter()
    run = await create_run(
        db,
        session_id=payload.session_id,
        agent_name='document-intelligence',
        status='running',
    )

    if payload.session_id:
        await add_message(
            db,
            session_id=payload.session_id,
            role='user',
            content=payload.question,
        )

    try:
        query_embedding = gemini.embed_query(payload.question)
        hits = await hybrid_retrieve(
            db,
            payload.question,
            query_embedding,
            payload.document_ids,
            payload.top_k,
        )

        context_parts: list[str] = []
        citations: list[Citation] = []
        for index, hit in enumerate(hits, start=1):
            chunk = hit['chunk']
            document = hit['document']
            score = hit['score']
            context_parts.append(
                f'[{index}] {document.filename} page {chunk.page_number or "n/a"}: '
                f'{chunk.content}'
            )
            citations.append(
                Citation(
                    index=index,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    filename=document.filename,
                    page_number=chunk.page_number,
                    score=score,
                    excerpt=chunk.content[:400],
                )
            )

        return PreparedAnswer(
            started=started,
            run=run,
            citations=citations,
            context='\n\n'.join(context_parts),
            sources_used=len(citations),
        )
    except Exception as exc:
        run.status = 'failed'
        run.error_message = str(exc)[:2000]
        run.latency_ms = (time.perf_counter() - started) * 1000
        await db.commit()
        raise


async def answer_question(db: AsyncSession, gemini: GeminiService, payload) -> AgentAnswer:
    prepared = await _prepare_answer(db, gemini, payload)

    try:
        answer = gemini.generate_grounded_answer(payload.question, prepared.context)
        if payload.session_id:
            await add_message(
                db,
                session_id=payload.session_id,
                role='assistant',
                content=answer,
                metadata_json={
                    'format': 'markdown',
                    'citations': [
                        citation.model_dump(mode='json')
                        for citation in prepared.citations
                    ],
                },
            )

        prepared.run.status = 'completed'
        prepared.run.latency_ms = (time.perf_counter() - prepared.started) * 1000
        await db.commit()

        return AgentAnswer(
            answer_markdown=answer,
            citations=prepared.citations,
            run=AgentRunInfo(
                id=prepared.run.id,
                agent='document-intelligence',
                latency_ms=prepared.run.latency_ms,
            ),
            retrieval=RetrievalInfo(sources_used=prepared.sources_used),
        )
    except Exception as exc:
        prepared.run.status = 'failed'
        prepared.run.error_message = str(exc)[:2000]
        prepared.run.latency_ms = (time.perf_counter() - prepared.started) * 1000
        await db.commit()
        raise


async def stream_question(db: AsyncSession, gemini: GeminiService, payload):
    prepared = await _prepare_answer(db, gemini, payload)

    async def event_stream():
        answer_parts: list[str] = []
        try:
            yield sse_event(
                'meta',
                {
                    'run': {
                        'id': str(prepared.run.id),
                        'agent': 'document-intelligence',
                    },
                    'retrieval': {'sources_used': prepared.sources_used},
                    'citations': [
                        citation.model_dump(mode='json')
                        for citation in prepared.citations
                    ],
                },
            )

            async for delta in gemini.stream_grounded_answer(
                payload.question,
                prepared.context,
            ):
                answer_parts.append(delta)
                yield sse_event('token', {'delta': delta})

            answer = ''.join(answer_parts)
            if payload.session_id:
                await add_message(
                    db,
                    session_id=payload.session_id,
                    role='assistant',
                    content=answer,
                    metadata_json={
                        'format': 'markdown',
                        'citations': [
                            citation.model_dump(mode='json')
                            for citation in prepared.citations
                        ],
                    },
                )

            prepared.run.status = 'completed'
            prepared.run.latency_ms = (time.perf_counter() - prepared.started) * 1000
            await db.commit()
            yield sse_event(
                'done',
                {
                    'run_id': str(prepared.run.id),
                    'latency_ms': prepared.run.latency_ms,
                },
            )
        except Exception as exc:
            prepared.run.status = 'failed'
            prepared.run.error_message = str(exc)[:2000]
            prepared.run.latency_ms = (time.perf_counter() - prepared.started) * 1000
            await db.commit()
            if isinstance(exc, AlectosError):
                yield sse_event(
                    'error',
                    {'detail': exc.message, 'code': exc.code},
                )
            else:
                yield sse_event(
                    'error',
                    {'detail': 'Internal server error', 'code': 'internal_error'},
                )

    return event_stream()
