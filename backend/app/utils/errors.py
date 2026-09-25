"""
Shared error-handling utilities.
Phase 1: generic exception handler scaffold.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("silentvoice.errors")


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler — never leaks stack traces in production."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again.",
        },
    )


def register_exception_handlers(app: Any) -> None:
    """Attach all custom exception handlers to the FastAPI app."""
    app.add_exception_handler(Exception, generic_exception_handler)
