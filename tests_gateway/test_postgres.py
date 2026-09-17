"""Integration tests require a disposable PostgreSQL database, never production.
Run: TEST_GATEWAY_DATABASE_URL=postgresql://... python -m pytest tests_gateway/test_postgres.py -q
"""
import asyncio
import os
from pathlib import Path
from uuid import uuid4
import asyncpg
import pytest
from fastapi import HTTPException
from gateway.store import Store


def test_atomic_quota_ownership_and_refund():
    url = os.getenv('TEST_GATEWAY_DATABASE_URL')
    if not url: pytest.skip('Disposable PostgreSQL URL not supplied')
    async def run():
        schema = 'test_gateway_' + uuid4().hex
        admin = await asyncpg.connect(url)
        await admin.execute(f'CREATE SCHEMA {schema}')
        pool = await asyncpg.create_pool(url, min_size=1, max_size=5, server_settings={'search_path': schema})
        try:
            async with pool.acquire() as conn:
                await conn.execute(Path('gateway/schema.sql').read_text())
            store = Store(pool)
            attempts = [uuid4(), uuid4()]
            results = await asyncio.gather(*(store.reserve('alice','document-intelligence',i,True,1) for i in attempts), return_exceptions=True)
            assert sum(r is None for r in results) == 1
            assert sum(isinstance(r,HTTPException) for r in results) == 1
            winner = attempts[next(i for i,r in enumerate(results) if r is None)]
            await store.finish('alice','document-intelligence',winner,'failed')
            replacement = uuid4()
            await store.reserve('alice','document-intelligence',replacement,True,1)
            await store.finish('alice','document-intelligence',replacement,'completed')
            with pytest.raises(HTTPException) as err:
                await store.reserve('alice','document-intelligence',uuid4(),True,1)
            assert err.value.status_code == 403
            await store.reserve('bob','document-intelligence',uuid4(),True,1)
            doc_id = uuid4()
            await store.own('alice','document',doc_id)
            await store.check_scope('alice',[doc_id])
            with pytest.raises(HTTPException): await store.check_scope('bob',[doc_id])
            disabled_run = uuid4()
            await store.reserve('tester','document-intelligence',disabled_run,False,1)
            await store.finish('tester','document-intelligence',disabled_run,'completed')
            assert (await store.usage('tester','document-intelligence',1,True))['remaining'] == 1
        finally:
            await pool.close()
            await admin.execute(f'DROP SCHEMA {schema} CASCADE')
            await admin.close()
    asyncio.run(run())
