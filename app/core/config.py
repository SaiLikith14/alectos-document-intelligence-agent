from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'Alectos Document Intelligence'
    app_env: str = 'development'
    api_v1_prefix: str = '/api/v1'
    database_url: str = 'postgresql+asyncpg://alectos:alectos@db:5432/alectos'
    cors_origins: str = 'http://localhost:3000,http://localhost:5173'
    gemini_api_key: str | None = None
    gemini_generation_model: str = 'gemini-2.5-flash'
    gemini_embedding_model: str = 'gemini-embedding-2'
    embedding_dimensions: int = 768
    upload_dir: str = 'uploads'
    max_upload_mb: int = 20
    default_top_k: int = 8
    rrf_k: int = 60

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    @field_validator('database_url')
    @classmethod
    def use_async_driver(cls, value: str) -> str:
        # Managed hosts (Render, Heroku, Supabase) hand out sync DSNs. SQLAlchemy's
        # async engine needs the asyncpg driver spelled out, so normalise it here
        # rather than making every deployment remember to rewrite the scheme.
        if value.startswith('postgres://'):
            return value.replace('postgres://', 'postgresql+asyncpg://', 1)
        if value.startswith('postgresql://'):
            return value.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
