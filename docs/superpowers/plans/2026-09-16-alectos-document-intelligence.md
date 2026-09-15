# Alectos Document Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable FastAPI + PostgreSQL/pgvector document intelligence backend that an existing UI can call.

**Architecture:** FastAPI provides HTTP endpoints; service and repository layers isolate business logic and persistence. PostgreSQL stores application records and vectors. Gemini provides embeddings and answer generation. Hybrid dense + full-text retrieval is fused with RRF.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, asyncpg, pgvector, PostgreSQL 16 + pgvector, google-genai, pypdf, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-16-alectos-document-intelligence-design.md`

## Global Constraints
- Embedding model: `gemini-embedding-2`
- Embedding size: 768
- Vector index: HNSW
- Retrieval: dense pgvector + PostgreSQL full-text search
- Fusion: Reciprocal Rank Fusion
- BYOK keys must not be persisted

---

### Task 1: Core configuration and API health
**Files:** `app/core/config.py`, `app/main.py`, `app/api/v1/health.py`, `tests/test_health.py`
- [ ] Write a failing health endpoint test
- [ ] Run the test and confirm failure
- [ ] Add settings and app factory
- [ ] Run test and confirm pass

### Task 2: Database models and connection
**Files:** `app/db/base.py`, `app/db/session.py`, `app/models/*.py`, `db/init.sql`, `tests/test_models.py`
- [ ] Write model metadata tests
- [ ] Confirm failure
- [ ] Implement SQLAlchemy models and pgvector column
- [ ] Add PostgreSQL extensions/index SQL
- [ ] Confirm tests pass

### Task 3: Chunking and RRF utilities
**Files:** `app/services/chunking.py`, `app/services/rrf.py`, `tests/test_chunking.py`, `tests/test_rrf.py`
- [ ] Write behavioral tests
- [ ] Confirm failure
- [ ] Implement deterministic chunking and RRF
- [ ] Confirm pass

### Task 4: Gemini services
**Files:** `app/services/gemini.py`, `app/api/dependencies.py`
- [ ] Add request-scoped key resolution
- [ ] Add embedding and generation client methods
- [ ] Validate embedding dimensionality

### Task 5: Repositories and hybrid retrieval
**Files:** `app/repositories/*.py`, `app/services/retrieval.py`
- [ ] Add CRUD repositories
- [ ] Add vector retrieval
- [ ] Add PostgreSQL full-text retrieval
- [ ] Fuse results with RRF

### Task 6: Document ingestion
**Files:** `app/services/document_ingestion.py`, `app/api/v1/documents.py`
- [ ] Validate PDF/TXT upload
- [ ] Extract text/page numbers
- [ ] Chunk, embed, persist chunks
- [ ] Return processing state

### Task 7: Agent query flow
**Files:** `app/services/document_agent.py`, `app/api/v1/agents.py`
- [ ] Embed query
- [ ] Retrieve/fuse context
- [ ] Generate grounded answer
- [ ] Return citations and agent-run metadata

### Task 8: Local deployment and documentation
**Files:** `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt`, `README.md`, `.vscode/launch.json`
- [ ] Add reproducible local stack
- [ ] Add startup and smoke-test instructions
- [ ] Run unit test suite
- [ ] Compile Python files
