# Alectos Backend Hardening Upgrade

This build adds:

- Clean API errors
- Session/document validation before database writes
- Failed-upload transaction rollback and temporary-file cleanup
- Markdown-first answer contract
- Structured citations/run/retrieval metadata
- SSE streaming endpoint
- Gemini error normalization
- Current Gemini SDK dependency range

## Easiest upgrade path

1. Stop Uvicorn with `Ctrl+C`.
2. Back up your existing `.env`.
3. Replace your project files with this package, but keep your existing `.env`.
4. Activate your virtual environment:

```bash
source .venv/bin/activate
```

5. Install/upgrade dependencies:

```bash
python -m pip install -U -r requirements.txt
```

6. Make sure PostgreSQL is still healthy:

```bash
docker compose ps
```

7. Start FastAPI:

```bash
uvicorn app.main:app --reload
```

8. Open `http://127.0.0.1:8000/docs`.

## Test the normal query endpoint

Use `POST /api/v1/agents/document-intelligence/query` with your real IDs:

```json
{
  "session_id": "YOUR_SESSION_ID",
  "question": "What technical skills are mentioned in this resume?",
  "document_ids": ["YOUR_DOCUMENT_ID"],
  "top_k": 8
}
```

The response now uses `answer_markdown` instead of `answer`.

## Test invalid IDs

Send a fake session UUID. You should receive a clean `404` instead of a PostgreSQL foreign-key traceback.

## Test streaming

Use `POST /api/v1/agents/document-intelligence/query/stream` with the same JSON body.

The endpoint emits these SSE event types:

- `meta`
- `token`
- `done`
- `error`

For the final frontend, use `fetch()` and read `response.body` as a stream. A native browser `EventSource` is not used because this is a POST endpoint with a JSON body.
