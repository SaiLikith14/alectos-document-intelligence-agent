"""Run: uvicorn gateway.main:create_gateway --factory --host 0.0.0.0 --port 8001"""
import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import UUID

import anyio
import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from gateway.auth import TokenVerifier, current_user
from gateway.policy import trial_applies
from gateway.settings import get_gateway_settings
from gateway.store import Store
from gateway.streaming import event, iter_events

AGENT = 'document-intelligence'
log = logging.getLogger(__name__)


class Query(BaseModel):
    session_id: UUID | None = None
    question: str = Field(min_length=1, max_length=10000)
    document_ids: list[UUID] = Field(min_length=1, max_length=50)
    top_k: int = Field(default=8, ge=1, le=20)


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class BodyLimitMiddleware:
    def __init__(self, app, upload_limit):
        self.app, self.upload_limit = app, upload_limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        limit = self.upload_limit if scope['path'] == '/api/v1/documents/upload' else 65536
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            body.extend(message.get('body', b''))
            if len(body) > limit:
                return await JSONResponse({'detail': 'Request too large'}, status_code=413)(scope, receive, send)
            if not message.get('more_body'): break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


def create_gateway(settings=None, store=None, client=None, verifier=None):
    config = settings or get_gateway_settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = config
        app.state.store = store or await Store.connect(config.database_url)
        app.state.verifier = verifier or TokenVerifier(config)
        app.state.client = client or httpx.AsyncClient(
            base_url=config.backend_url.rstrip('/'),
            headers={'X-Alectos-Gateway-Key': config.backend_gateway_secret},
            timeout=httpx.Timeout(config.gateway_timeout_seconds, connect=10),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=10),
            follow_redirects=False,
        )
        try:
            if store is None:
                async with app.state.store.pool.acquire() as conn:
                    await conn.execute('SELECT subject FROM gateway_users LIMIT 0')
            yield
        finally:
            if client is None: await app.state.client.aclose()
            if store is None: await app.state.store.pool.close()

    app = FastAPI(title='Alectos Gateway', lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware, upload_limit=(config.gateway_max_upload_mb + 1) * 1024 * 1024)
    app.add_middleware(CORSMiddleware, allow_origins=config.origins,
                       allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        # Do not log tokens, document contents, provider responses, or shared secrets.
        log.error('Gateway failure (%s)', type(exc).__name__)
        return JSONResponse({'detail': 'Gateway temporarily unavailable'}, status_code=503)

    def metered(user): return trial_applies(config.trial_enforcement_enabled, user, config.admins)

    async def backend_json(request, method, path, **kwargs):
        try:
            async with asyncio.timeout(config.gateway_timeout_seconds):
                response = await request.app.state.client.request(method, path, **kwargs)
        except (httpx.HTTPError, TimeoutError) as exc:
            raise HTTPException(502, 'Backend unavailable; request outcome may be unknown') from exc
        if not response.is_success:
            # Preserve useful status codes without exposing raw upstream error text.
            status = response.status_code if 400 <= response.status_code < 500 else 502
            raise HTTPException(status, 'Backend could not complete this request')
        try: return response.json()
        except ValueError as exc: raise HTTPException(502, 'Invalid backend response') from exc

    @app.get('/api/v1/health')
    async def health(): return {'status': 'ok', 'service': 'Alectos Gateway'}

    @app.get('/api/v1/me/usage')
    async def usage(request: Request, user: str = Depends(current_user)):
        return {'agents': [await request.app.state.store.usage(user, AGENT, config.trial_requests_per_agent, metered(user))]}

    @app.post('/api/v1/sessions', status_code=201)
    async def create_session(payload: SessionCreate, request: Request, user: str = Depends(current_user)):
        data = await backend_json(request, 'POST', '/api/v1/sessions', json=payload.model_dump())
        await request.app.state.store.own(user, 'session', UUID(data['id']))
        return data

    @app.get('/api/v1/sessions/{session_id}')
    async def read_session(session_id: UUID, request: Request, user: str = Depends(current_user)):
        await request.app.state.store.check_scope(user, [], session_id)
        return await backend_json(request, 'GET', f'/api/v1/sessions/{session_id}')

    @app.get('/api/v1/documents/{document_id}')
    async def read_document(document_id: UUID, request: Request, user: str = Depends(current_user)):
        await request.app.state.store.check_scope(user, [document_id])
        return await backend_json(request, 'GET', f'/api/v1/documents/{document_id}')

    @app.post('/api/v1/documents/upload', status_code=201)
    async def upload(request: Request, file: UploadFile = File(...), session_id: UUID | None = Form(None), user: str = Depends(current_user)):
        db = request.app.state.store
        await db.check_scope(user, [], session_id)
        if file.content_type not in {'application/pdf', 'text/plain'}:
            raise HTTPException(400, 'Upload PDF or TXT files only')
        payload = await file.read(config.gateway_max_upload_mb * 1024 * 1024 + 1)
        if not payload: raise HTTPException(400, 'File is empty')
        if len(payload) > config.gateway_max_upload_mb * 1024 * 1024:
            raise HTTPException(413, 'File too large')
        ticket = await db.reserve_upload(user, session_id, config.gateway_max_documents_per_user)
        try:
            data = await backend_json(request, 'POST', '/api/v1/documents/upload',
                                      files={'file': (file.filename or 'upload', payload, file.content_type)},
                                      data={'session_id': str(session_id)} if session_id else {})
            await db.finish_upload(user, ticket, UUID(data['id']))
            return data
        except HTTPException as exc:
            # A 4xx was explicitly rejected. Ambiguous network/5xx failures keep the slot
            # until an operator checks for an orphaned backend document.
            if exc.status_code < 500: await db.finish_upload(user, ticket)
            raise

    async def reserve(request, payload, user, request_id):
        await request.app.state.store.check_scope(user, payload.document_ids, payload.session_id)
        if not payload.question.strip(): raise HTTPException(422, 'Question must not be blank')
        await request.app.state.store.reserve(user, AGENT, request_id, metered(user), config.trial_requests_per_agent)

    async def finish(request, user, request_id, status):
        # Cleanup persists even if the browser disconnects. If persistence itself fails,
        # the original reservation stays blocked for explicit reconciliation.
        with anyio.CancelScope(shield=True):
            await request.app.state.store.finish(user, AGENT, request_id, status)

    @app.post('/api/v1/agents/document-intelligence/query')
    async def query(payload: Query, request: Request, user: str = Depends(current_user), request_id: UUID = Header(alias='Idempotency-Key')):
        await reserve(request, payload, user, request_id)
        status = 'uncertain'
        try:
            data = await backend_json(request, 'POST', f'/api/v1/agents/{AGENT}/query', json=payload.model_dump(mode='json'))
            if not isinstance(data.get('answer_markdown'), str) or not data['answer_markdown'].strip():
                raise HTTPException(502, 'Backend returned an empty or invalid answer')
            await finish(request, user, request_id, 'completed')
            status = 'completed'
            return data
        except HTTPException as exc:
            if exc.status_code < 500: status = 'failed'
            raise
        finally:
            if status != 'completed': await finish(request, user, request_id, status)

    @app.post('/api/v1/agents/document-intelligence/query/stream')
    async def query_stream(payload: Query, request: Request, user: str = Depends(current_user), request_id: UUID = Header(alias='Idempotency-Key')):
        await reserve(request, payload, user, request_id)
        # Cleanup is in the generator and response background task, covering disconnects
        # both before and after the first yielded SSE event.
        async def stream():
            status = 'uncertain'
            saw_text = False
            try:
                async with asyncio.timeout(config.gateway_timeout_seconds):
                    async with request.app.state.client.stream('POST', f'/api/v1/agents/{AGENT}/query/stream', json=payload.model_dump(mode='json')) as response:
                        if not response.is_success:
                            status = 'failed' if response.status_code < 500 else 'uncertain'
                            await finish(request, user, request_id, status)
                            yield event('error', {'detail': 'Backend could not complete this request', 'code': 'upstream_error'})
                            return
                        if 'text/event-stream' not in response.headers.get('content-type', ''):
                            raise ValueError('Unexpected stream type')
                        async for name, data in iter_events(response.aiter_bytes()):
                            if not isinstance(data, dict): raise ValueError('Invalid event payload')
                            if name == 'token':
                                if not isinstance(data.get('delta'), str): raise ValueError('Invalid token payload')
                                saw_text = saw_text or bool(data['delta'].strip())
                            if name == 'error':
                                status = 'failed'
                                await finish(request, user, request_id, status)
                                yield event('error', {'detail': 'The agent could not complete the answer. Your trial allowance was released.', 'code': 'agent_error'})
                                return
                            if name == 'done':
                                if not saw_text: raise ValueError('Empty answer')
                                await finish(request, user, request_id, 'completed')
                                status = 'completed'
                                yield event(name, data)
                                return
                            if name in {'meta', 'token'}: yield event(name, data)
                        raise ValueError('Stream ended without done')
            except Exception:
                yield event('error', {'detail': 'The response was interrupted. Check usage before retrying.', 'code': 'stream_interrupted'})
            finally:
                if status != 'completed': await finish(request, user, request_id, status)
        from starlette.background import BackgroundTask
        return StreamingResponse(stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
                                 background=BackgroundTask(finish, request, user, request_id, 'uncertain'))

    return app
