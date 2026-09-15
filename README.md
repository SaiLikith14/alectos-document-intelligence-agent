# Alectos Document Intelligence Backend

FastAPI backend for a document-intelligence RAG agent using PostgreSQL + pgvector, Gemini embeddings, PostgreSQL full-text search, Reciprocal Rank Fusion, and Gemini answer generation.

## 1. Prerequisites
- Python 3.12+
- Docker Desktop
- VS Code
- A Gemini API key

## 2. Quick start with Docker
```bash
cp .env.example .env
# Add GEMINI_API_KEY to .env if you want a server-side key

docker compose up --build
```

Open:
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

## 3. Local Python + Docker database
Start only PostgreSQL:
```bash
docker compose up -d db
```

Create a virtual environment:
```bash
python -m venv .venv
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Copy env file and run:
```bash
cp .env.example .env
uvicorn app.main:app --reload
```

## 4. BYOK from your UI
Send the user's Gemini key only in the request header:
```text
X-Gemini-API-Key: <user-key>
```
The application does not persist this header value.

## 5. Create a session
```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"title":"My document chat"}'
```

## 6. Upload a document
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H 'X-Gemini-API-Key: YOUR_KEY' \
  -F 'file=@sample.pdf'
```

## 7. Query the document agent
```bash
curl -X POST http://localhost:8000/api/v1/agents/document-intelligence/query \
  -H 'Content-Type: application/json' \
  -H 'X-Gemini-API-Key: YOUR_KEY' \
  -d '{
    "question":"Summarize the main risks",
    "document_ids":["YOUR_DOCUMENT_UUID"],
    "top_k":8
  }'
```

## 8. Frontend contract
Upload:
- `POST /api/v1/documents/upload`
- multipart form field: `file`
- optional form field: `session_id`

Query:
- `POST /api/v1/agents/document-intelligence/query`
- JSON: `question`, `document_ids`, optional `session_id`, optional `top_k`

## Notes
This first version supports PDF and TXT ingestion. Local files are stored in `uploads/`. Replace this with object storage before production if needed.

## Hardened API contract

### Non-streaming query

`POST /api/v1/agents/document-intelligence/query`

Returns Markdown separately from citation metadata:

```json
{
  "answer_markdown": "## Technical skills\n\n- Python [1]",
  "citations": [
    {
      "index": 1,
      "document_id": "...",
      "chunk_id": "...",
      "filename": "resume.pdf",
      "page_number": 1,
      "score": 0.016,
      "excerpt": "..."
    }
  ],
  "run": {
    "id": "...",
    "agent": "document-intelligence",
    "latency_ms": 842.4
  },
  "retrieval": {
    "sources_used": 3
  }
}
```

Render `answer_markdown` in the frontend with a Markdown renderer. Keep typography, spacing, citation pills, source cards, copy buttons, and responsive layout in the UI layer.

### Streaming query

`POST /api/v1/agents/document-intelligence/query/stream`

The response uses Server-Sent Events over a streamed POST response. A frontend should read the `fetch()` response body stream. Event types are:

- `meta`: run metadata, retrieval count, and citations
- `token`: one generated Markdown delta in `data.delta`
- `done`: run ID and final latency
- `error`: safe error detail and machine-readable error code

### Error behavior

- Missing Gemini key: `401`
- Missing session or document: `404`
- Unsupported upload: `400`
- Oversized upload: `413`
- Gemini upstream/rate-limit failures: `502`
- Unexpected server failures: `500` with a safe generic message

Invalid session/document IDs are validated before agent-run creation, so PostgreSQL foreign-key errors are not exposed to the client.

### Failed upload behavior

Document creation and chunk insertion stay in one transaction until ingestion succeeds. If extraction, embedding, or indexing fails, the transaction is rolled back and the uploaded temporary file is removed.
