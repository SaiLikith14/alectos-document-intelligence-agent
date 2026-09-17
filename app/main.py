import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.gateway_auth import GatewayOnlyMiddleware

import app.models  # noqa: F401 - register all SQLAlchemy models
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AlectosError
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "UPDATE document_chunks SET content_tsv = "
                "to_tsvector('english', content) WHERE content_tsv IS NULL"
            )
        )
        await conn.execute(
            text(
                'CREATE INDEX IF NOT EXISTS ix_document_chunks_tsv '
                'ON document_chunks USING GIN (content_tsv)'
            )
        )
        await conn.execute(
            text(
                'CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw '
                'ON document_chunks USING hnsw (embedding vector_cosine_ops) '
                'WHERE embedding IS NOT NULL'
            )
        )
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version='0.2.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# Outermost: direct clients cannot bypass the public gateway.
app.add_middleware(GatewayOnlyMiddleware)


@app.exception_handler(AlectosError)
async def handle_alectos_error(_: Request, exc: AlectosError):
    return JSONResponse(
        status_code=exc.status_code,
        content={'detail': exc.message, 'code': exc.code},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception):
    logger.exception('Unhandled Alectos backend error', exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={'detail': 'Internal server error', 'code': 'internal_error'},
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get('/')
async def root():
    return {'service': settings.app_name, 'docs': '/docs'}
