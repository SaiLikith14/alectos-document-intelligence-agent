"""Reject direct backend access. The shared secret must never reach a browser."""
import os
import secrets
from starlette.responses import JSONResponse


class GatewayOnlyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        # Health contains no user data. Everything else, including docs, is protected.
        if scope['method'] == 'GET' and scope['path'] == '/api/v1/health':
            return await self.app(scope, receive, send)
        secret = os.environ.get('BACKEND_GATEWAY_SECRET', '')
        if len(secret) < 32:
            response = JSONResponse({'detail': 'Gateway protection is not configured'}, status_code=503)
        else:
            values = [v for k, v in scope['headers'] if k.lower() == b'x-alectos-gateway-key']
            valid = len(values) == 1 and secrets.compare_digest(values[0], secret.encode())
            if valid:
                return await self.app(scope, receive, send)
            response = JSONResponse({'detail': 'Gateway access required'}, status_code=401)
        await response(scope, receive, send)
