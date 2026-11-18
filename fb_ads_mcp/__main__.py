"""Start the server.

  python -m fb_ads_mcp            -> HTTP server (for Render / Railway / Claude connector)
                                     with the dashboard website at /dashboard
  python -m fb_ads_mcp --stdio    -> stdio (for Claude Desktop / Claude Code on your computer)
"""

from __future__ import annotations

import hmac
import os
import sys
from urllib.parse import parse_qs

from starlette.responses import JSONResponse, RedirectResponse

from .server import mcp, settings


class SecretKeyMiddleware:
    """Blocks every request that does not carry the MCP_AUTH_TOKEN.

    The key can be sent as:
      - URL:    https://your-app.onrender.com/mcp?key=YOUR_SECRET   (use this for Claude)
      - header: Authorization: Bearer YOUR_SECRET
    """

    OPEN_PATHS = {"/health", "/"}

    def __init__(self, app, secret: str | None):
        self.app = app
        self.secret = secret

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.OPEN_PATHS:
            return await self.app(scope, receive, send)
        if not self.secret:
            resp = JSONResponse({"error": "MCP is off. Set MCP_AUTH_TOKEN to turn it on."},
                                status_code=503)
            return await resp(scope, receive, send)
        given = ""
        qs = parse_qs(scope.get("query_string", b"").decode())
        if qs.get("key"):
            given = qs["key"][0]
        for name, value in scope.get("headers", []):
            if name == b"authorization" and value.lower().startswith(b"bearer "):
                given = value[7:].decode().strip()
        if not given or not hmac.compare_digest(given, self.secret):
            resp = JSONResponse({"error": "unauthorized"}, status_code=401)
            return await resp(scope, receive, send)
        return await self.app(scope, receive, send)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    return JSONResponse({"ok": True, "service": "facebook-ads-mcp"})


@mcp.custom_route("/", methods=["GET"])
async def root(_request):
    return JSONResponse({"ok": True, "mcp_endpoint": "/mcp"})


class DashboardRouter:
    """Sends /dashboard... to the dashboard website and everything else to MCP."""

    def __init__(self, mcp_app, dashboard_app):
        self.mcp_app = mcp_app
        self.dashboard_app = dashboard_app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path == "/dashboard" or path.startswith("/dashboard/"):
            return await self.dashboard_app(scope, receive, send)
        if path == "/":
            resp = RedirectResponse("/dashboard", status_code=307)
            return await resp(scope, receive, send)
        return await self.mcp_app(scope, receive, send)


def _dashboard_on() -> bool:
    return os.getenv("DASHBOARD_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


def build_http_app():
    dashboard = _dashboard_on()
    if not settings.mcp_auth_token and not dashboard:
        raise SystemExit(
            "MCP_AUTH_TOKEN is not set. Set a long random secret before starting the "
            "HTTP server, otherwise anyone could control your ads."
        )
    if not settings.mcp_auth_token:
        print("MCP_AUTH_TOKEN is not set: the MCP endpoint is OFF, only the dashboard runs.",
              file=sys.stderr)
    app = SecretKeyMiddleware(mcp.streamable_http_app(), settings.mcp_auth_token)
    if dashboard:
        from .dashboard import create_dashboard_app

        app = DashboardRouter(app, create_dashboard_app())
    return app


def main() -> None:
    if "--stdio" in sys.argv or os.getenv("MCP_TRANSPORT") == "stdio":
        mcp.run(transport="stdio")
        return
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(build_http_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
