import asyncio
import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError


class TokenVerifier:
    def __init__(self, settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.auth_jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

    def verify(self, token: str) -> str:
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256':
                raise jwt.InvalidTokenError('Unsupported algorithm')
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=['RS256'], audience=self.settings.auth_audience,
                                issuer=self.settings.auth_issuer,
                                options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
            subject = claims['sub']
            if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
                raise jwt.InvalidTokenError('Invalid subject')
            return subject
        except PyJWKClientConnectionError as exc:
            raise HTTPException(503, 'Login verification temporarily unavailable') from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(401, 'Invalid or expired login token', headers={'WWW-Authenticate': 'Bearer'}) from exc


async def current_user(request: Request) -> str:
    value = request.headers.get('authorization', '')
    parts = value.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 16384:
        raise HTTPException(401, 'Login required', headers={'WWW-Authenticate': 'Bearer'})
    subject = await asyncio.to_thread(request.app.state.verifier.verify, parts[1])
    if subject in request.app.state.settings.blocked:
        raise HTTPException(403, 'Account access disabled')
    return subject
