# Alectos gateway patch: copy and deployment guide

This package implements the gateway alternative discussed in the conversation. It is a patch for the uploaded alectos_backend.zip, not a standalone replacement backend. Merge its folders into your existing alectos_backend folder. Do not replace the whole app folder or delete files that are not included.

## What changes

Browser -> authenticated gateway -> protected existing FastAPI RAG backend.

- Login is always required for agent, upload, session, and document endpoints
- Gateway verifies RS256 JWT signature, issuer, audience, expiration, issued-at time, and subject
- One free completed request per user per agent when enforcement is enabled
- Trial enforcement is OFF by default for testing; testing runs do not spend the later allowance
- Admin exemption uses verified user IDs in server configuration
- Document/session IDs are checked against gateway ownership records even when session_id is omitted
- Database reservations prevent concurrent trial bypass and duplicate request IDs
- Direct backend calls require a server-only shared secret
- No payments or paid subscription handling is included

## Exact copy locations

All paths are relative to your existing alectos_backend folder.

| Action | Path | Purpose |
|---|---|---|
| Replace | app/main.py | Register the backend gateway-secret guard |
| Add | app/core/gateway_auth.py | Reject direct backend access without the server secret |
| Add | gateway/__init__.py | Gateway package |
| Add | gateway/main.py | Public endpoints, upload bounds, backend proxy, stream metering |
| Add | gateway/settings.py | Server-side authentication and trial settings |
| Add | gateway/auth.py | Login token verification |
| Add | gateway/policy.py | Trial rules and document ownership checks |
| Add | gateway/store.py | PostgreSQL resource mappings and atomic quota reservations |
| Add | gateway/streaming.py | Bounded SSE parsing |
| Add | gateway/schema.sql | Three additive gateway tables and indexes |
| Add | gateway/migrate.py | Apply the additive schema |
| Add | requirements-gateway.txt | Existing dependencies plus JWT verification dependency |
| Add | Dockerfile.gateway | Build the separate gateway service |
| Add/merge | .dockerignore | Exclude credentials, uploads, and development files from images |
| Add | .gateway.env.example | Gateway configuration template |
| Add | docker-compose.gateway.yml | Optional local two-service deployment plus database/migration |
| Add | tests_gateway/ | Security, HTTP-flow, and PostgreSQL concurrency tests |

Existing requirements.txt, Dockerfile, database models, retrieval, chunking, and Gemini code are unchanged. Existing RAG concerns from the review still apply.

## 1. Configure login (Firebase example)

No login provider existed in the supplied backend. This patch supports a configured RS256 issuer with a JWKS endpoint. The example is Firebase Authentication, suitable for Google login, but enabling Firebase is still required in your own project.

1. In your Firebase project, enable Authentication and the Google sign-in provider
2. Register your web app and authorize the frontend's actual domains
3. Copy .gateway.env.example to .gateway.env locally
4. Set AUTH_AUDIENCE to the Firebase project ID
5. Set AUTH_ISSUER to https://securetoken.google.com/ followed by that same project ID
6. Keep the Firebase AUTH_JWKS_URL shown in the template
7. Put your Firebase UID in ADMIN_SUBJECTS for an exemption when trial enforcement is enabled
8. Set CORS_ORIGINS to the exact frontend origins, separated by commas

The frontend must send Firebase ID tokens from user.getIdToken(), not Google OAuth access tokens or Firebase custom tokens. No Firebase service account private key is required by this JWKS-based verifier. This verifier does not check Firebase revocation/disabled-user status in real time. BLOCKED_SUBJECTS provides an immediate server-controlled denylist after service restart; integrate provider revocation checks if required before launch.

Official references:
- https://firebase.google.com/docs/auth/admin/verify-id-tokens
- https://pyjwt.readthedocs.io/en/stable/usage.html

## 2. Protect the existing backend

Generate a new secret locally:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

Set BACKEND_GATEWAY_SECRET to the same generated value on BOTH backend and gateway services. It must be at least 32 characters. This secret is never an authentication token for the browser and must not be placed in AI Studio frontend code, VITE_* variables, or source control.

The backend guard intentionally rejects non-health requests with 503 when the secret is absent or too short. Requests with an invalid/missing secret get 401. This applies even if trial enforcement is disabled.

Do not overwrite your existing .env file. Add BACKEND_GATEWAY_SECRET to your hosting provider's backend environment settings. Keep GEMINI_API_KEY only on the RAG backend. The gateway does not accept or forward browser-supplied Gemini keys.

For local uvicorn, load .env explicitly with --env-file .env so the backend guard can read the environment variable.

Existing frontend calls will stop working after backend protection is deployed until the frontend is connected to the gateway with login tokens. Roll out the gateway and frontend together, preferably in staging first. If the backend can use a private network, use it. Otherwise use HTTPS to protect the shared secret in transit.

## 3. Configure and migrate the gateway

Set these server variables (or use .gateway.env locally):

    DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
    BACKEND_URL=https://YOUR-EXISTING-BACKEND-HOST
    BACKEND_GATEWAY_SECRET=<the same generated secret>
    AUTH_ISSUER=<configured token issuer>
    AUTH_AUDIENCE=<configured token audience>
    AUTH_JWKS_URL=<configured HTTPS JWKS endpoint>
    TRIAL_ENFORCEMENT_ENABLED=false
    TRIAL_REQUESTS_PER_AGENT=1

The gateway may use your existing PostgreSQL database. The migration adds only gateway_users, gateway_resources, and gateway_requests. Back up the database first. Do not change AUTH_ISSUER after recording users without a planned identity migration.

From the project root:

    pip install -r requirements-gateway.txt
    python -m gateway.migrate

The migration is repeatable and does not change the existing RAG tables. It must be run before the gateway starts. URLs containing reserved password characters must be URL-encoded.

## 4. Run two services

Existing RAG backend start command:

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env

New public gateway start command:

    uvicorn gateway.main:create_gateway --factory --host 0.0.0.0 --port 8001

On a hosting platform that supplies a PORT variable, use its assigned port in each service's start command. The gateway's backend URL must resolve to the RAG service, never the gateway itself. Docker deployments can use the included Dockerfile.gateway.

Optional local Docker setup:

- Set GEMINI_API_KEY, BACKEND_GATEWAY_SECRET, and LOCAL_DB_PASSWORD in your existing .env
- Populate .gateway.env with the login-provider settings
- For an existing PostgreSQL volume, LOCAL_DB_PASSWORD must match that database's existing password; setting it does not rotate existing credentials
- Stop your old local Compose services to avoid sharing a database volume between two PostgreSQL processes
- Run: docker compose -f docker-compose.gateway.yml up --build
- Only the gateway is exposed on localhost:8001; database and RAG service stay on the Docker network
- This file is a standalone local alternative, not an overlay on docker-compose.yml

## 5. AI Studio frontend changes still required

Set the API base URL to the gateway. Remove the hardcoded direct Render-backend fallback. If you retain a development proxy, point it at the gateway too.

Every protected request needs:

    Authorization: Bearer <current Firebase ID token>

Every query, including streamed queries, ALSO needs:

    Idempotency-Key: <a UUID generated for that question submission>

Generate the UUID once per submission. Reuse it only when checking/retrying the same submission; the gateway returns 409 instead of generating another answer. For a new submission after a confirmed failure, generate a new UUID. Completed response replay is not implemented.

GET /api/v1/me/usage returns an agents array. remaining is null when the user has no enforced trial limit. pending_requests identifies active or uncertain requests. Refresh it after every run and after errors. Do not treat remaining alone as permission to ignore pending_requests.

Existing upload, session, citation, and SSE field names are preserved. Frontend streaming must mark success only on done, never on an error event or network EOF. A usage limit returns HTTP 403 with detail.code=trial_exhausted; an already-running or repeated request returns 409.

Use FRONTEND_INSTRUCTIONS.md as the AI Studio prompt. This ZIP contains backend and gateway code; it does not include a finished login screen.

## 6. Trial behavior and failure handling

Set TRIAL_ENFORCEMENT_ENABLED=true and restart the gateway when ready. Your ADMIN_SUBJECTS remain exempt. There is no browser-controlled bypass.

- One successful completed answer consumes one allowance, including an insufficient-information answer
- Explicit streamed agent errors release the allowance
- Explicit 4xx query rejections release the allowance
- Connection failures, gateway timeouts, abrupt stream endings, and crashes may leave the backend outcome unknown. These become uncertain/reserved and stay blocked until reviewed
- We deliberately do not expire these automatically: a backend run may still be generating after its browser disconnects
- One request can be active per user/agent, even when trial enforcement is off
- Ten documents/upload reservations per user and 20 MB per file are defaults, independently configurable
- Upload slots with unknown outcomes also remain reserved; review orphans before releasing them

To reconcile, FIRST confirm the backend run is no longer active and whether it completed. During a maintenance window stop traffic for that account. In a database transaction, lock its gateway_users row with SELECT ... FOR UPDATE, then update only the exact gateway_requests row (subject, agent, request_id). Use completed if it succeeded, failed if it definitely failed. Never bulk-reset all users or auto-refund based only on elapsed time. A failed status frees the quota but the old idempotency key remains unusable.

For a stuck upload, confirm the backend outcome. If successful, convert the exact upload reservation to an owned document mapping with the returned backend document UUID. If it definitely failed and left no document, remove that exact upload reservation. Do not guess an owner for a document.

## 7. Existing data

Documents and sessions created before this gateway do not have gateway ownership records. They are intentionally inaccessible through the gateway. Sign in and upload test documents again. For real existing customer documents, perform a reviewed ownership migration using authoritative user records; do not assign all legacy data to whoever logs in first.

## 8. Verification and remaining release work

Run:

    python -m pytest tests tests_gateway -q

For the real database concurrency test, provide a DISPOSABLE PostgreSQL URL whose user can create/drop a temporary schema:

    TEST_GATEWAY_DATABASE_URL=postgresql://... python -m pytest tests_gateway/test_postgres.py -q

That test uses a uniquely named schema and removes it afterward. Never point it at production.

Read VERIFICATION.md for exactly what was run during preparation. Before public launch, verify live Firebase login, PostgreSQL concurrency, actual multi-chunk ingestion, backend calls, stream disconnects, and hosting timeouts. Add per-user/IP rate limits, provider budget monitoring, document deletion/retention, and the RAG quality fixes from the review. One free request per account does not prevent someone from registering many accounts.

The patch does not fix the existing model batching assumptions, synchronous ingestion/model calls, or answer grounding. It is not a certification of production readiness.
