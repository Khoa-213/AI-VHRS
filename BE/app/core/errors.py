"""One error envelope for the whole API: {"error": {"code", "message", "details"}}."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app")

# Raised by the DB state-guard triggers (invalid order/production transition, BR-xx).
STATE_CONFLICT_SQLSTATE = "P0409"
LOCK_TIMEOUT_SQLSTATE = "55P03"                  # lock_not_available: `lock_timeout` ran out (db/session.py, AR-02)
_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = None
        if exc.status == 429 and isinstance(exc.details, dict):
            headers = {"Retry-After": str(exc.details.get("retry_after_seconds", 60))}
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"field": ".".join(map(str, e["loc"][1:])), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "Dữ liệu không hợp lệ.", details), status_code=422)

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == STATE_CONFLICT_SQLSTATE:
            return JSONResponse(_body("STATE_CONFLICT", str(exc.orig).splitlines()[0]), status_code=409)
        if sqlstate == LOCK_TIMEOUT_SQLSTATE:
            return JSONResponse(_body("RESOURCE_BUSY", "Dữ liệu đang được một thao tác khác xử lý. Vui lòng thử lại sau giây lát."),
                                status_code=409, headers={"Retry-After": "5"})
        if isinstance(exc, IntegrityError):
            return JSONResponse(_body("CONFLICT", "Dữ liệu xung đột với ràng buộc hiện có."), status_code=409)
        log.exception("Database error")
        return JSONResponse(_body("INTERNAL_ERROR", "Lỗi hệ thống."), status_code=500)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        """AR-05: an unknown route or method answered {"detail": ...}, the only replies without the error envelope. `detail`
        is kept beside it for anything that still reads the old shape."""
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        body = {**_body(code, str(exc.detail)), "detail": exc.detail}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))


def internal_error_response() -> JSONResponse:
    """What an unexpected failure answers (AR-05): the envelope, never a stack trace or the exception text."""
    return JSONResponse(_body("INTERNAL_ERROR", "Lỗi hệ thống."), status_code=500)
