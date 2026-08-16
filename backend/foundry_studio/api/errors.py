"""API exception model + global handlers.

Every error the API raises uses a stable ``message_key`` (see ``i18n.py``)
plus optional params, so the frontend can render localized text.  HTTP status
codes remain meaningful for tooling.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from foundry_studio.i18n import localize


class ApiError(Exception):
    """Raised by route handlers; converted to a localized JSON error."""

    def __init__(
        self,
        message_key: str,
        *,
        status_code: int = 400,
        params: dict[str, str] | None = None,
        detail: str | None = None,
    ):
        super().__init__(message_key)
        self.message_key = message_key
        self.status_code = status_code
        self.params = params or {}
        self.detail = detail


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):  # noqa: ARG001
        locale = request.query_params.get("lang", "en")
        message = localize(exc.message_key, locale, exc.params)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "message_key": exc.message_key,
                "params": exc.params,
                "message": message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):  # noqa: ARG001
        locale = request.query_params.get("lang", "en")
        message = localize("error.unknown", locale, {"detail": str(exc)})
        return JSONResponse(
            status_code=500,
            content={
                "message_key": "error.unknown",
                "params": {"detail": str(exc)},
                "message": message,
                "detail": str(exc),
            },
        )
