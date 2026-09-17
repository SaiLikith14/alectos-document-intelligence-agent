from functools import lru_cache
from urllib.parse import urlparse
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    database_url: str
    backend_url: str = 'http://127.0.0.1:8000'
    backend_gateway_secret: str = Field(min_length=32)
    # Research agent (MCP). Left blank, its routes are simply not registered,
    # so the gateway still runs with only the document agent deployed.
    research_backend_url: str = ''
    research_backend_api_key: str = ''
    auth_issuer: str
    auth_audience: str
    auth_jwks_url: str
    admin_subjects: str = ''
    blocked_subjects: str = ''
    trial_enforcement_enabled: bool = False
    trial_requests_per_agent: int = Field(default=1, ge=1, le=1000)
    gateway_max_upload_mb: int = Field(default=20, ge=1, le=100)
    gateway_max_documents_per_user: int = Field(default=10, ge=1)
    cors_origins: str = 'http://localhost:3000,http://localhost:5173'
    gateway_timeout_seconds: int = Field(default=180, ge=10, le=600)
    model_config = SettingsConfigDict(env_file='.gateway.env', extra='ignore')

    @model_validator(mode='after')
    def validate_endpoints(self):
        for name in ('auth_issuer', 'auth_jwks_url'):
            if urlparse(getattr(self, name)).scheme != 'https':
                raise ValueError(f'{name} must use HTTPS')
        for name in ('backend_url', 'research_backend_url'):
            raw = getattr(self, name)
            if not raw:
                continue
            url = urlparse(raw)
            if url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError(f'{name.upper()} must be a fixed HTTP(S) server URL')
            if url.path not in {'', '/'}:
                raise ValueError(f'{name.upper()} must not contain a path')
        if self.research_backend_url and not self.research_backend_api_key:
            raise ValueError('RESEARCH_BACKEND_API_KEY is required when RESEARCH_BACKEND_URL is set')
        if not self.auth_audience.strip():
            raise ValueError('AUTH_AUDIENCE must not be empty')
        return self

    @property
    def research_enabled(self): return bool(self.research_backend_url)

    @property
    def admins(self): return {s.strip() for s in self.admin_subjects.split(',') if s.strip()}

    @property
    def blocked(self): return {s.strip() for s in self.blocked_subjects.split(',') if s.strip()}

    @property
    def origins(self): return [s.strip() for s in self.cors_origins.split(',') if s.strip()]


@lru_cache
def get_gateway_settings(): return GatewaySettings()
