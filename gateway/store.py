from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import asyncpg
from fastapi import HTTPException
from gateway.policy import check_allowance, validate_owned_resources


def postgres_dsn(url):
    return url.replace('postgresql+asyncpg://', 'postgresql://', 1)


class Store:
    def __init__(self, pool): self.pool = pool

    @classmethod
    async def connect(cls, url):
        return cls(await asyncpg.create_pool(postgres_dsn(url), min_size=1, max_size=10, command_timeout=15))

    @asynccontextmanager
    async def locked_user(self, subject):
        # All quota changes for one user serialize in PostgreSQL across workers.
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('INSERT INTO gateway_users(subject) VALUES($1) ON CONFLICT DO NOTHING', subject)
                await conn.fetchval('SELECT subject FROM gateway_users WHERE subject=$1 FOR UPDATE', subject)
                yield conn

    async def own(self, subject, kind, resource_id, session_id=None):
        async with self.locked_user(subject) as conn:
            await conn.execute('INSERT INTO gateway_resources(kind,resource_id,subject,session_id) VALUES($1,$2,$3,$4)',
                               kind, UUID(str(resource_id)), subject, UUID(str(session_id)) if session_id else None)

    async def check_scope(self, subject, document_ids, session_id=None):
        async with self.pool.acquire() as conn:
            ids = [UUID(str(i)) for i in document_ids]
            if session_id: ids.append(UUID(str(session_id)))
            records = await conn.fetch('SELECT kind,resource_id,session_id FROM gateway_resources WHERE subject=$1 AND resource_id=ANY($2::uuid[])', subject, ids)
        validate_owned_resources(records, document_ids, session_id)

    async def reserve_upload(self, subject, session_id, limit):
        ticket = uuid4()
        async with self.locked_user(subject) as conn:
            count = await conn.fetchval("SELECT count(*) FROM gateway_resources WHERE subject=$1 AND kind IN ('document','upload')", subject)
            if count >= limit: raise HTTPException(403, 'Document allowance reached')
            await conn.execute("INSERT INTO gateway_resources(kind,resource_id,subject,session_id) VALUES('upload',$1,$2,$3)", ticket, subject, session_id)
        return ticket

    async def finish_upload(self, subject, ticket, document_id=None):
        async with self.locked_user(subject) as conn:
            row = await conn.fetchrow("DELETE FROM gateway_resources WHERE subject=$1 AND kind='upload' AND resource_id=$2 RETURNING session_id", subject, ticket)
            if not row: raise RuntimeError('Upload reservation missing')
            if document_id:
                await conn.execute("INSERT INTO gateway_resources(kind,resource_id,subject,session_id) VALUES('document',$1,$2,$3)", UUID(str(document_id)), subject, row['session_id'])

    async def reserve(self, subject, agent, request_id, metered, allowance, stale_after=180):
        async with self.locked_user(subject) as conn:
            existing = await conn.fetchval('SELECT status FROM gateway_requests WHERE subject=$1 AND agent=$2 AND request_id=$3', subject, agent, request_id)
            if existing:
                raise HTTPException(409, {'code': 'duplicate_request', 'status': existing, 'message': 'This request ID has already been used. No new run was started.'})
            # One active request per user/agent even in testing mode. A row only
            # blocks while the run it represents could still be going: past the
            # gateway's own timeout the upstream call has certainly ended, and a
            # row abandoned at 'uncertain' would otherwise wedge the agent
            # permanently with no way to clear it. Allowance accounting below is
            # unaffected — it counts 'uncertain' regardless of age, so nothing is
            # silently refunded.
            active = await conn.fetchval(
                "SELECT count(*) FROM gateway_requests WHERE subject=$1 AND agent=$2 "
                "AND status IN ('reserved','uncertain') "
                "AND updated_at > now() - make_interval(secs => $3::double precision)",
                subject, agent, float(stale_after))
            if active: raise HTTPException(409, {'code': 'request_pending', 'message': 'A request is active or needs reconciliation.'})
            if metered:
                count = await conn.fetchval("SELECT count(*) FROM gateway_requests WHERE subject=$1 AND agent=$2 AND metered AND status IN ('reserved','completed','uncertain')", subject, agent)
                check_allowance(count, allowance)
            await conn.execute("INSERT INTO gateway_requests(subject,agent,request_id,status,metered) VALUES($1,$2,$3,'reserved',$4)", subject, agent, request_id, metered)

    async def finish(self, subject, agent, request_id, status):
        if status not in {'completed', 'failed', 'uncertain'}: raise ValueError('Invalid final status')
        async with self.locked_user(subject) as conn:
            await conn.execute("UPDATE gateway_requests SET status=$4,updated_at=now() WHERE subject=$1 AND agent=$2 AND request_id=$3 AND status='reserved'", subject, agent, request_id, status)

    async def usage(self, subject, agent, allowance, metered):
        async with self.pool.acquire() as conn:
            consumed = await conn.fetchval("SELECT count(*) FROM gateway_requests WHERE subject=$1 AND agent=$2 AND metered AND status IN ('reserved','completed','uncertain')", subject, agent)
            pending = await conn.fetch("SELECT request_id,status FROM gateway_requests WHERE subject=$1 AND agent=$2 AND status IN ('reserved','uncertain')", subject, agent)
        return {'agent': agent, 'trial_enforced': metered, 'remaining': max(0, allowance-consumed) if metered else None,
                'pending_requests': [{'request_id': str(r['request_id']), 'status': r['status']} for r in pending]}
