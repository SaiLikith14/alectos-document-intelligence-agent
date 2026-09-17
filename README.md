# Alectos Document Intelligence

A document-intelligence RAG agent: PostgreSQL + pgvector, Gemini embeddings, PostgreSQL
full-text search, Reciprocal Rank Fusion, and Gemini answer generation — behind an
authentication gateway that verifies Firebase ID tokens and scopes every document to the
user who uploaded it.

## Architecture

```
browser ──► gateway ──────────────► backend ──► Postgres + Gemini
            verifies Firebase       refuses any request that
            ID tokens, enforces     does not carry the shared
            ownership, meters       secret header
            trial usage
```

Two services, one database:

| | Port | Faces | Role |
|---|---|---|---|
| **gateway** (`gateway/`) | 8001 | the browser | Verifies RS256 Firebase tokens against JWKS, enforces per-user ownership of sessions and documents, meters trial usage with idempotency keys, proxies to the backend |
| **backend** (`app/`) | 8000 | the gateway only | Ingestion, chunking, embeddings, hybrid retrieval, answer generation |

`GatewayOnlyMiddleware` rejects any request to the backend that lacks
`X-Alectos-Gateway-Key`, so the backend is never callable from a browser even when it is
reachable on the network. `/api/v1/health` is the single exception.

## Documentation

| Document | Covers |
|---|---|
| [GATEWAY_SETUP.md](GATEWAY_SETUP.md) | Configuring the gateway, auth issuer, and shared secret |
| [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) | Deploying both services and Postgres to Render |
| [FRONTEND_INSTRUCTIONS.md](FRONTEND_INSTRUCTIONS.md) | The contract a frontend must honour |
| [VERIFICATION.md](VERIFICATION.md) | What was tested and how |
| [UPGRADE_GUIDE.md](UPGRADE_GUIDE.md) | Moving from the pre-gateway version |

## Prerequisites

- Python 3.12+
- Docker Desktop
- A Gemini API key
- A Firebase project with Google sign-in enabled

## Running locally

### 1. Configuration

```bash
cp .env.example .env              # backend
cp .gateway.env.example .gateway.env   # gateway
```

Generate a shared secret and put the **same value** in both files:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In `.gateway.env`, set `AUTH_ISSUER` to
`https://securetoken.google.com/<firebase-project-id>` and `AUTH_AUDIENCE` to the
project ID itself.

### 2. Docker Compose

```bash
docker compose -f docker-compose.gateway.yml up --build
```

This brings up Postgres, the backend, the gateway schema migration, and the gateway.
Only the gateway is published, on `localhost:8001`.

### 3. Or run the services directly

```bash
docker compose up -d db
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-gateway.txt
python -m gateway.migrate
```

Then, in two terminals:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

```bash
uvicorn gateway.main:create_gateway --factory --host 0.0.0.0 --port 8001
```

> `--env-file .env` is required. `GatewayOnlyMiddleware` reads
> `BACKEND_GATEWAY_SECRET` from the process environment, not from the settings file, so
> without it every request returns `503 Gateway protection is not configured`.

Verify:

```bash
curl http://localhost:8001/api/v1/health
```

## API

Every endpoint below is served by the **gateway** and requires
`Authorization: Bearer <firebase-id-token>`.

### Create a session

```bash
curl -X POST http://localhost:8001/api/v1/sessions \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"My document chat"}'
```

### Upload a document

PDF and TXT only, `GATEWAY_MAX_UPLOAD_MB` cap, `GATEWAY_MAX_DOCUMENTS_PER_USER` per user.

```bash
curl -X POST http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer $ID_TOKEN" \
  -F 'file=@sample.pdf' \
  -F "session_id=$SESSION_ID"
```

### Query

`Idempotency-Key` is required and must be a UUID. Reusing a key for a different question
is rejected rather than silently re-run, so a retried request can never consume a second
trial allowance.

```bash
curl -X POST http://localhost:8001/api/v1/agents/document-intelligence/query \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "question":"Summarize the main risks",
    "document_ids":["YOUR_DOCUMENT_UUID"],
    "top_k":8
  }'
```

### Usage

```bash
curl http://localhost:8001/api/v1/me/usage -H "Authorization: Bearer $ID_TOKEN"
```

```json
{
  "agents": [
    {
      "agent": "document-intelligence",
      "trial_enforced": false,
      "remaining": null,
      "pending_requests": []
    }
  ]
}
```

`remaining` is `null` when trial enforcement is off. `pending_requests` is a **list**, not
a count — a non-empty list means a run is still in flight and a new one will be refused.

## Response contract

### Non-streaming query

Markdown is returned separately from citation metadata:

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
  "run": { "id": "...", "agent": "document-intelligence", "latency_ms": 842.4 },
  "retrieval": { "sources_used": 3 }
}
```

Render `answer_markdown` with a Markdown renderer. Typography, citation pills, source
cards, and layout belong to the UI layer.

### Streaming query

`POST /api/v1/agents/document-intelligence/query/stream` returns Server-Sent Events over
a streamed POST response — read `fetch()`'s response body stream.

| Event | Payload |
|---|---|
| `meta` | run metadata, retrieval count, citations |
| `token` | one Markdown delta in `data.delta` |
| `done` | run ID and final latency |
| `error` | safe detail plus a machine-readable `code` |

Treat only `done` as success. A stream that ends without it was interrupted, and the
gateway releases the trial reservation in that case.

### Status codes

| Code | Meaning |
|---|---|
| `401` | Missing, expired, or invalid ID token |
| `403` | Trial allowance exhausted (`code: trial_exhausted`), subject blocked, document allowance reached, or resource owned by another user |
| `404` | Session or document not found |
| `409` | Duplicate idempotency key, or another run still pending |
| `413` | Upload exceeds the configured limit |
| `422` | Malformed payload |
| `502` | Backend or Gemini upstream failure |
| `503` | Gateway misconfigured — usually a missing shared secret |

Invalid session and document IDs are validated before an agent run is created, so
PostgreSQL foreign-key errors never reach the client.

## Behaviour worth knowing

**Uploads are transactional.** Document creation and chunk insertion stay in one
transaction until ingestion succeeds. If extraction, embedding, or indexing fails, the
transaction rolls back and the temporary file is removed.

**Trial accounting survives disconnects.** Reservations are released in a shielded
cancel scope, so a browser that closes mid-stream still frees the allowance. If the
release itself fails, the reservation stays blocked deliberately, for an operator to
reconcile rather than silently granting a free run.

**The Gemini key is server-side only.** Earlier versions accepted a per-request
`X-Gemini-API-Key` header from the browser. The gateway does not forward it, so
`GEMINI_API_KEY` must be configured on the backend. Never expose a provider key to a
frontend.

**Local files are incidental.** PDFs are parsed into chunks and embeddings at upload
time; every later query reads those rows from Postgres. The file in `uploads/` is not
consulted again.

## License

See [LICENSE](LICENSE).
