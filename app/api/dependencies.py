from fastapi import Header

from app.core.config import get_settings
from app.core.errors import AuthenticationError


async def get_gemini_api_key(x_gemini_api_key: str | None = Header(default=None)) -> str:
    settings = get_settings()
    key = (x_gemini_api_key or settings.gemini_api_key or '').strip()
    if not key:
        raise AuthenticationError(
            'Gemini API key is required. Send X-Gemini-API-Key or configure GEMINI_API_KEY.'
        )
    return key
