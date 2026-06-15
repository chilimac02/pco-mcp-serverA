"""FastAPI entry point for the PCO MCP server.

Routing layout:
  GET  /                       → plain-text landing page
  GET  /health                 → liveness probe (Docker healthcheck)
  *    /auth/*                 → OAuth flow (login, start, callback, logout)
  *    /mcp                    → FastMCP Streamable HTTP transport,
                                  gated by SessionMiddleware

Run locally:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.routing import Route

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.db import init_db
from app.mcp.middleware import SessionMiddleware
from app.mcp.server import get_streamable_http_app


logger = logging.getLogger("pco_mcp")


# Build the FastMCP Starlette sub-app once at import time. It has its own
# lifespan (manages an internal task group for streaming sessions), which we
# wire into FastAPI's lifespan below — without that, the session manager
# never starts and POST /mcp times out.
#
# FastMCP returns a Starlette app whose single route at "/" routes through
# Starlette's path-matching (which trips on trailing-slash redirects when
# mounted). To sidestep that, we pull out the inner ASGI endpoint
# (`StreamableHTTPASGIApp`) and mount it directly — Starlette's router is
# bypassed entirely, so /mcp and /mcp/ both flow straight to the endpoint.
_mcp_asgi_app = get_streamable_http_app()
_mcp_endpoint = _mcp_asgi_app.routes[0].endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Combined startup/shutdown: our own init + FastMCP's session manager."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting PCO MCP server on port %s", settings.port)
    logger.info("PCO redirect URI: %s", settings.pco_redirect_uri)

    await init_db()
    logger.info("SQLite ready at %s", settings.db_path)

    # Enter FastMCP's lifespan context — starts the streamable HTTP session
    # manager. Without this, the /mcp endpoint accepts requests but the
    # internal session task group is never running, so calls hang.
    async with _mcp_asgi_app.router.lifespan_context(_mcp_asgi_app):
        logger.info("FastMCP streamable HTTP session manager started")
        yield
        logger.info("Stopping FastMCP streamable HTTP session manager")

    logger.info("Shutting down PCO MCP server")


app = FastAPI(
    title="PCO MCP Server",
    description="Multi-user OAuth MCP server for Planning Center Services.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe used by Docker healthcheck."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index() -> PlainTextResponse:
    """Friendly landing page so people who hit the root URL aren't confused."""
    return PlainTextResponse(
        "PCO MCP Server is running.\n"
        "Visit /auth/login to connect your Planning Center account.\n"
        "MCP endpoint: /mcp\n"
        "Admin: /admin (Basic auth)"
    )


# --- Mounted routers -------------------------------------------------------
# Phase 2: OAuth flow.
app.include_router(auth_router)
# Phase 10: admin page (Basic-auth gated; 503 if ADMIN_USERNAME/PASSWORD unset).
app.include_router(admin_router)

# Phase 4: FastMCP Streamable HTTP at /mcp, gated by SessionMiddleware.
#
# We register an explicit Starlette `Route` rather than `app.mount(...)`:
#   - Mount adds a prefix dispatcher that triggers Starlette's
#     auto-redirect-to-trailing-slash (307 on POST /mcp). Many MCP clients
#     won't follow POST redirects, so /mcp would silently break for them.
#   - A plain Route matches /mcp exactly with no slash games. Starlette
#     detects that the endpoint instance has __call__(scope, receive, send)
#     and dispatches it as an ASGI app — perfect for our middleware chain.
#
# The StreamableHTTPASGIApp endpoint ignores the URL path; it dispatches on
# HTTP method + request body. So registering it at exactly /mcp is enough.
_wrapped_mcp = SessionMiddleware(_mcp_endpoint)
app.router.routes.append(
    Route("/mcp", endpoint=_wrapped_mcp, methods=["GET", "POST", "DELETE"])
)
