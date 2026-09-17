"""HTTP integration with deterministic backend and identity-provider doubles.
PostgreSQL concurrency is tested separately in test_postgres.py.
"""
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from gateway.main import create_gateway
from gateway.settings import GatewaySettings
from gateway.policy import validate_owned_resources


class MemoryStore:
    def __init__(self): self.resources = []; self.requests = {}
    async def check_scope(self, user, ids, session_id=None):
        validate_owned_resources([r for r in self.resources if r['subject']==user],ids,session_id)
    async def own(self,user,kind,resource_id,session_id=None):
        self.resources.append(dict(subject=user,kind=kind,resource_id=resource_id,session_id=session_id))
    async def reserve(self,user,agent,request_id,metered,allowance):
        if request_id in self.requests: raise HTTPException(409,'Duplicate')
        self.requests[request_id] = {'status':'reserved','metered':metered}
    async def finish(self,user,agent,request_id,status):
        if self.requests[request_id]['status']=='reserved': self.requests[request_id]['status']=status
    async def usage(self,*args): return {}


class Identity:
    def verify(self,token): return token


def setup_gateway(stream_body=None):
    store = MemoryStore()
    doc_id=uuid4()
    store.resources.append(dict(subject='alice',kind='document',resource_id=doc_id,session_id=None))
    calls=[]
    def respond(request):
        calls.append(request)
        if request.url.path.endswith('/stream'):
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content=stream_body)
        if request.url.path.endswith('/sessions'):
            return httpx.Response(201,json={'id':str(uuid4()),'title':'demo'})
        return httpx.Response(200,json={'answer_markdown':'An answer [1]'})
    upstream=httpx.AsyncClient(transport=httpx.MockTransport(respond),base_url='https://backend.test',headers={'X-Alectos-Gateway-Key':'s'*48})
    settings=GatewaySettings(database_url='postgresql://unused',backend_gateway_secret='s'*48,
        auth_issuer='https://issuer.test',auth_audience='test',auth_jwks_url='https://issuer.test/keys')
    return create_gateway(settings,store,upstream,Identity()),store,doc_id,calls


def test_login_and_ownership_before_any_backend_call():
    app,store,doc,calls=setup_gateway()
    with TestClient(app) as client:
        body={'question':'test','document_ids':[str(doc)]}
        key={'Idempotency-Key':str(uuid4())}
        assert client.post('/api/v1/agents/document-intelligence/query',json=body,headers=key).status_code==401
        assert client.post('/api/v1/agents/document-intelligence/query',json=body,headers={**key,'Authorization':'Bearer bob'}).status_code==404
        assert calls==[]
        result=client.post('/api/v1/agents/document-intelligence/query',json=body,headers={**key,'Authorization':'Bearer alice'})
        assert result.status_code==200
        assert list(store.requests.values())[0]=={'status':'completed','metered':False}
        assert len(calls)==1
        assert calls[0].headers.get('authorization') is None


@pytest.mark.parametrize('body,expected',[
    (b'event: token\ndata: {"delta":"answer"}\n\nevent: done\ndata: {}\n\n','completed'),
    (b'event: error\ndata: {"detail":"failed"}\n\n','failed'),
    (b'event: token\ndata: {"delta":"partial"}\n\n','uncertain'),
    (b'event: done\ndata: {}\n\n','uncertain'),
])
def test_stream_quota_outcome(body,expected):
    app,store,doc,calls=setup_gateway(body)
    with TestClient(app) as client:
        response=client.post('/api/v1/agents/document-intelligence/query/stream',
            json={'question':'test','document_ids':[str(doc)]},
            headers={'Authorization':'Bearer alice','Idempotency-Key':str(uuid4())})
        assert response.status_code==200
        assert list(store.requests.values())[0]['status']==expected
        assert ('event: done' in response.text)==(expected=='completed')


def test_duplicate_request_and_missing_key_do_not_repeat_upstream():
    app,store,doc,calls=setup_gateway()
    with TestClient(app) as client:
        headers={'Authorization':'Bearer alice','Idempotency-Key':str(uuid4())}
        body={'question':'test','document_ids':[str(doc)]}
        url='/api/v1/agents/document-intelligence/query'
        assert client.post(url,json=body,headers=headers).status_code==200
        assert client.post(url,json=body,headers=headers).status_code==409
        assert client.post(url,json=body,headers={'Authorization':'Bearer alice'}).status_code==422
        assert len(calls)==1


def test_new_session_owned_by_authenticated_user():
    app,store,doc,calls=setup_gateway()
    with TestClient(app) as client:
        response=client.post('/api/v1/sessions',json={'title':'demo'},headers={'Authorization':'Bearer alice'})
        assert response.status_code==201
        assert store.resources[-1]['kind']=='session'
        assert store.resources[-1]['subject']=='alice'


def test_body_limit_prevents_upstream_call():
    app,store,doc,calls=setup_gateway()
    with TestClient(app) as client:
        response=client.post('/api/v1/sessions',content=b'x'*65537,headers={'Authorization':'Bearer alice'})
        assert response.status_code==413
        assert calls==[]
