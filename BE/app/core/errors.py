"""One error envelope for the whole API: {"error": {"code", "message", "details"}}."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

log = logging.getLogger("app")

# Raised by the DB state-guard triggers (invalid order/production transition, BR-xx).
STATE_CONFLICT_SQLSTATE = "P0409"


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
        if isinstance(exc, IntegrityError):
            return JSONResponse(_body("CONFLICT", "Dữ liệu xung đột với ràng buộc hiện có."), status_code=409)
        log.exception("Database error")
        return JSONResponse(_body("INTERNAL_ERROR", "Lỗi hệ thống."), status_code=500)
