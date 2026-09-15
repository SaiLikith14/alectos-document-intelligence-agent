# Alectos Document Intelligence Backend Design

## Goal
Build a production-oriented FastAPI backend for a document intelligence RAG agent with PostgreSQL + pgvector, Gemini embeddings/generation, hybrid retrieval, Reciprocal Rank Fusion, citations, sessions, and a clean API contract for an existing web UI.

## Architecture
The frontend communicates only with FastAPI. FastAPI delegates persistence to repositories, AI calls to Gemini services, and retrieval to isolated retrieval components. PostgreSQL stores application data and vectors; pgvector provides dense retrieval while PostgreSQL full-text search provides sparse lexical retrieval. Reciprocal Rank Fusion merges the two rankings.

## Data Model
- users: optional user identity boundary for future authentication
- sessions: conversation/session lifecycle
- documents: uploaded document metadata and processing state
- document_chunks: extracted chunks, page metadata, tsvector content, and VECTOR(768) embedding
- messages: user/assistant conversation history
- agent_runs: latency/status/metadata for observability

## API
- GET /api/v1/health
- POST /api/v1/sessions
- GET /api/v1/sessions/{session_id}
- POST /api/v1/documents/upload
- GET /api/v1/documents/{document_id}
- POST /api/v1/agents/document-intelligence/query

## Retrieval
1. Embed query using gemini-embedding-2 at 768 dimensions
2. Dense pgvector search using cosine distance
3. PostgreSQL full-text search using websearch_to_tsquery
4. Fuse rankings using RRF
5. Build grounded context with document/page/chunk provenance
6. Generate answer with Gemini
7. Return answer and citations

## BYOK
The API accepts an optional `X-Gemini-API-Key` request header. The key is used only to create a request-scoped Gemini client and is never persisted by this application.

## File Ingestion
Version 1 accepts PDF and TXT. PDF text is extracted locally with pypdf, split page-by-page, chunked, embedded, and stored. Files are saved under a local upload directory for development. Object storage can replace this later without changing the API contract.

## Deployment
Local: Docker Compose runs PostgreSQL/pgvector and FastAPI. Production can deploy the container to Cloud Run/Render/Railway and use a managed PostgreSQL provider that supports pgvector.
