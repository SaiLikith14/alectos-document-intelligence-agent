# Deploying Alectos to Render

Three pieces go up: a Postgres database, the RAG backend, and the auth gateway.
[`render.yaml`](render.yaml) declares all three, so Render creates them together.

```
browser ──► gateway (public)  ──► backend (secret-gated) ──► Postgres + Gemini
            verifies Firebase      refuses any request
            ID tokens, meters      without the shared key
            trial usage
```

Only the gateway is meant to receive browser traffic. The backend is deployed as a
web service because Render's free tier has no private networking, but
`GatewayOnlyMiddleware` rejects every request that arrives without
`X-Alectos-Gateway-Key`, so a direct hit returns `401` rather than data.

---

## Before you start

- A GitHub repo Render can read (this one).
- A Gemini API key.
- A Firebase project with Google sign-in enabled — you need its project ID.
- The origin your frontend will be served from, for CORS.

---

## 1. Create the Blueprint

In the Render dashboard: **New → Blueprint**, pick this repository, and Render reads
`render.yaml`. It will prompt for the values deliberately kept out of version control:

| Service | Variable | Value |
|---|---|---|
| `alectos-backend` | `GEMINI_API_KEY` | your Gemini key |
| `alectos-gateway` | `BACKEND_URL` | *leave blank for now — step 3* |
| `alectos-gateway` | `AUTH_ISSUER` | `https://securetoken.google.com/<firebase-project-id>` |
| `alectos-gateway` | `AUTH_AUDIENCE` | `<firebase-project-id>` |
| `alectos-gateway` | `CORS_ORIGINS` | your frontend origin, e.g. `https://alectos.vercel.app` |

`BACKEND_GATEWAY_SECRET` is **not** in that list. Render generates it on the backend and
the gateway reads the same value via `fromService`, so the two always agree and the
secret never appears in a file you can commit.

## 2. Let the first deploy finish

The backend runs migrations at startup: it creates the `vector` extension, the tables,
the full-text index, and the HNSW vector index. The gateway runs `python -m gateway.migrate`
before serving, which applies its own schema. Both are idempotent, so restarts are safe.

## 3. Point the gateway at the backend

Copy the backend's URL from its Render page — `https://alectos-backend.onrender.com` —
and set it as `BACKEND_URL` on **alectos-gateway**, then redeploy the gateway.

It must be a bare origin: scheme required, no trailing path, no credentials. The settings
validator rejects anything else at boot rather than failing later on a request.

## 4. Verify

```bash
curl https://alectos-gateway.onrender.com/api/v1/health
```

Expect `{"status":"ok","service":"Alectos Gateway"}`.

Then confirm the backend is actually sealed:

```bash
curl -i https://alectos-backend.onrender.com/api/v1/sessions
```

Expect `401` with `Gateway access required`. If you get anything else, stop and check
that `BACKEND_GATEWAY_SECRET` is set on the backend — a missing secret returns `503`,
and the service is not safe to leave public until that is fixed.

## 5. Point the frontend at the gateway

In the frontend's environment:

```
VITE_ALECTOS_API_BASE_URL=https://alectos-gateway.onrender.com
```

Add that frontend origin to `CORS_ORIGINS` on the gateway. The gateway allows only
`GET` and `POST`, and only the `Authorization`, `Content-Type`, and `Idempotency-Key`
headers — the frontend needs nothing else.

---

## Things that will bite you on the free tier

**Services sleep after 15 minutes idle.** The first request afterwards pays a cold start
of roughly 30–50 seconds, and a query wakes *two* services in sequence.
`GATEWAY_TIMEOUT_SECONDS` is 180, which absorbs this, but the first question after a
quiet spell will feel slow.

**Free Postgres expires after 30 days.** Render deletes it. Export anything you care
about, or move to a paid instance before then.

**Uploaded files do not survive a restart.** `UPLOAD_DIR` is `/tmp/uploads`, and Render's
disk is ephemeral. This is deliberate rather than broken: a PDF is parsed into chunks and
embeddings at upload time, and every later query reads those rows from Postgres, never
the original file. Losing the file loses nothing the agent needs. Attach a persistent
disk only if you later want to re-parse or hand originals back to users.

**Trial enforcement ships off.** `TRIAL_ENFORCEMENT_ENABLED=false` means every signed-in
user runs unlimited queries. Login and per-user ownership are enforced regardless — the
flag governs only the request counter. Turn it on once you want the one-free-request
policy, and set `ADMIN_SUBJECTS` to the Firebase UIDs that should be exempt.

## Rotating the shared secret

Set a new `BACKEND_GATEWAY_SECRET` on the backend, wait for it to redeploy, then
redeploy the gateway so it picks up the new value. Requests in the window between the
two will fail with `401`. Rotate during a quiet period, and never move the secret into
a `VITE_*` variable — anything prefixed `VITE_` is compiled into the browser bundle.
