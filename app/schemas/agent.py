from uuid import UUID

from pydantic import BaseModel, Field


class AgentQuery(BaseModel):
    session_id: UUID | None = None
    question: str = Field(min_length=1, max_length=10000)
    document_ids: list[UUID] = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=20)


class Citation(BaseModel):
    index: int
    document_id: UUID
    chunk_id: UUID
    filename: str
    page_number: int | None
    score: float
    excerpt: str


class AgentRunInfo(BaseModel):
    id: UUID
    agent: str
    latency_ms: float | None = None


class RetrievalInfo(BaseModel):
    sources_used: int


class AgentAnswer(BaseModel):
    answer_markdown: str
    citations: list[Citation]
    run: AgentRunInfo
    retrieval: RetrievalInfo
