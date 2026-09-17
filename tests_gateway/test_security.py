import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def test_backend_blocks_direct_access(monkeypatch):
    from app.core.gateway_auth import GatewayOnlyMiddleware
    monkeypatch.setenv('BACKEND_GATEWAY_SECRET', 's' * 48)
    app = FastAPI()
    app.add_middleware(GatewayOnlyMiddleware)
    @app.get('/private')
    def private(): return {'ok': True}
    client = TestClient(app)
    assert client.get('/private').status_code == 401
    assert client.get('/private', headers={'X-Alectos-Gateway-Key': 'wrong'}).status_code == 401
    assert client.get('/private', headers={'X-Alectos-Gateway-Key': 's' * 48}).status_code == 200
    monkeypatch.delenv('BACKEND_GATEWAY_SECRET')
    assert TestClient(app).get('/private').status_code == 503


def test_jwt_signature_issuer_audience_and_expiry():
    from gateway.auth import TokenVerifier
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(auth_jwks_url='https://issuer.test/keys', auth_issuer='https://issuer.test', auth_audience='alectos')
    verifier = TokenVerifier(settings)
    verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    claims = {'sub': 'alice', 'iss': settings.auth_issuer, 'aud': 'alectos', 'iat': int(time.time()), 'exp': int(time.time()) + 60}
    token = jwt.encode(claims, key, algorithm='RS256')
    assert verifier.verify(token) == 'alice'
    for bad in [dict(claims, aud='wrong'), dict(claims, iss='https://other'), dict(claims, exp=1), dict(claims, sub='')]:
        with pytest.raises(HTTPException) as err:
            verifier.verify(jwt.encode(bad, key, algorithm='RS256'))
        assert err.value.status_code == 401
    with pytest.raises(HTTPException): verifier.verify(jwt.encode(claims, other, algorithm='RS256'))
    with pytest.raises(HTTPException): verifier.verify(jwt.encode(claims, 'x' * 48, algorithm='HS256'))


def test_trial_disabled_and_admin_do_not_consume_trial():
    from gateway.policy import trial_applies, check_allowance
    assert not trial_applies(False, 'alice', set())
    assert not trial_applies(True, 'admin', {'admin'})
    assert trial_applies(True, 'alice', {'admin'})
    check_allowance(0, 1)
    with pytest.raises(HTTPException) as err: check_allowance(1, 1)
    assert err.value.status_code == 403


def test_ownership_checked_without_session():
    from gateway.policy import validate_owned_resources
    doc_id = str(uuid4())
    records = [{'kind': 'document', 'resource_id': doc_id, 'session_id': None}]
    validate_owned_resources(records, [doc_id], None)
    with pytest.raises(HTTPException): validate_owned_resources([], [doc_id], None)
    with pytest.raises(HTTPException): validate_owned_resources(records, [doc_id], str(uuid4()))


def test_sse_parser_handles_crlf_and_split_chunks():
    from gateway.streaming import iter_events
    async def source():
        for part in [b'event: token\r', b'\ndata: {"delta":"hello"}\r\n\r', b'\nevent: done\ndata: {}\n\n']:
            yield part
    async def run(): return [e async for e in iter_events(source())]
    events = asyncio.run(run())
    assert [e[0] for e in events] == ['token', 'done']
    assert events[0][1] == {'delta': 'hello'}


def test_sse_rejects_unterminated_or_oversized_frames():
    from gateway.streaming import iter_events
    async def source(): yield b'event: done\ndata: {}'
    async def run(): return [e async for e in iter_events(source())]
    with pytest.raises(ValueError): asyncio.run(run())
