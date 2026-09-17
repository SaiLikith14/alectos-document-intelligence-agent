"""Run once before starting the gateway: python -m gateway.migrate"""
import asyncio
from pathlib import Path
import asyncpg
from gateway.settings import get_gateway_settings
from gateway.store import postgres_dsn


async def main():
    settings = get_gateway_settings()
    conn = await asyncpg.connect(postgres_dsn(settings.database_url))
    try:
        async with conn.transaction():
            await conn.execute(Path(__file__).with_name('schema.sql').read_text())
    finally:
        await conn.close()
    print('Gateway schema ready. Existing RAG tables were not modified.')


if __name__ == '__main__': asyncio.run(main())
