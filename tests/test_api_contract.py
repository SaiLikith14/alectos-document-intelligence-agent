from uuid import uuid4

import pytest

from app.core.errors import ResourceNotFoundError
from app.schemas.agent import AgentAnswer, AgentRunInfo, Citation, RetrievalInfo
from app.services.guards import validate_document_scope
from app.services.streaming import sse_event


class FakeDocument:
    def __init__(self, document_id, session_id):
        self.id = document_id
        self.session_id = session_id


def test_agent_answer_uses_markdown_contract():
    run_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    payload = AgentAnswer(
        answer_markdown='## Skills\n\n- Python',
        citations=[Citation(
            index=1,
            document_id=document_id,
            chunk_id=chunk_id,
            filename='resume.pdf',
            page_number=1,
            score=0.01,
            excerpt='Python',
        )],
        run=AgentRunInfo(id=run_id, agent='document-intelligence', latency_ms=42.0),
        retrieval=RetrievalInfo(sources_used=1),
    )
    data = payload.model_dump(mode='json')
    assert data['answer_markdown'].startswith('## Skills')
    assert 'answer' not in data
    assert data['run']['id'] == str(run_id)
    assert data['retrieval']['sources_used'] == 1


def test_document_scope_rejects_missing_documents():
    requested = [uuid4(), uuid4()]
    docs = [FakeDocument(requested[0], None)]
    with pytest.raises(ResourceNotFoundError, match='Document not found'):
        validate_document_scope(docs, requested, None)


def test_document_scope_rejects_document_from_other_session():
    session_id = uuid4()
    other_session_id = uuid4()
    document_id = uuid4()
    docs = [FakeDocument(document_id, other_session_id)]
    with pytest.raises(ResourceNotFoundError, match='not available in this session'):
        validate_document_scope(docs, [document_id], session_id)


def test_sse_event_serializes_named_json_event():
    encoded = sse_event('token', {'delta': 'Hello'})
    assert encoded == 'event: token\ndata: {"delta":"Hello"}\n\n'
