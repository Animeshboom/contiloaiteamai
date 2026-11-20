"""Domain errors, translated to HTTP responses by handlers registered in main.py.

Services raise these; routers stay thin and never build HTTP errors for business rules.
"""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Locked(AppError):
    status_code = 429
    code = "account_locked"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"
