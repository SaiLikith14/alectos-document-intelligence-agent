class AlectosError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = 'alectos_error'):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class BadRequestError(AlectosError):
    def __init__(self, message: str):
        super().__init__(message, status_code=400, code='bad_request')


class AuthenticationError(AlectosError):
    def __init__(self, message: str):
        super().__init__(message, status_code=401, code='authentication_error')


class ResourceNotFoundError(AlectosError):
    def __init__(self, message: str):
        super().__init__(message, status_code=404, code='not_found')


class UpstreamServiceError(AlectosError):
    def __init__(self, message: str):
        super().__init__(message, status_code=502, code='upstream_service_error')
