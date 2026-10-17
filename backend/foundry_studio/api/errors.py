"""API exception model + global handlers.

Every error the API raises uses a stable ``message_key`` (see ``i18n.py``)
plus optional params, so the frontend can render localized text.  HTTP status
codes remain meaningful for tooling.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        """Keep validation failures in the same localized envelope as ApiError.

        Without this, FastAPI returns its bare ``{"detail": [...]}`` 422, which
        (a) carries no ``message_key`` so the frontend cannot localize it, and
        (b) masks domain errors like an unknown model, which callers expect as
        a 404 ``error.model_not_found``.
        """
        errors = exc.errors()
        # A bad `model` / `engine_mode` value is a domain lookup failure, not a
        # malformed request -> report it the way the route handlers do.
        for err in errors:
            if err.get("loc") and err["loc"][-1] == "model":
                locale = request.query_params.get("lang", "en")
                bad = err.get("input")
                params = {"model": str(bad)}
                return JSONResponse(
                    status_code=404,
                    content={
                        "message_key": "error.model_not_found",
                        "params": params,
                        "message": localize("error.model_not_found", locale, params),
                        "detail": None,
                    },
                )

        locale = request.query_params.get("lang", "en")
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
            for e in errors
        ) or "invalid request"
        params = {"detail": detail}
        return JSONResponse(
            status_code=422,
            content={
                "message_key": "error.validation_failed",
                "params": params,
                "message": localize("error.validation_failed", locale, params),
                "detail": detail,
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
