"""Client ads dashboard website.

Pages (all under /dashboard):
  /dashboard                 all clients: spend, leads, CPL, CPC, ROAS
  /dashboard/client/<name>   one client: totals, chart per day, campaigns
  /dashboard/login           password page

Settings (environment variables):
  DASHBOARD_PASSWORD   password to open the dashboard (needed for real data)
  DASHBOARD_DEMO       "true" = show fake numbers (also used when there is no token)
  DASHBOARD_CACHE_SECONDS  how long to keep numbers before asking Meta again (default 300)
  DASHBOARD_SECRET     optional extra secret for the login cookie
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ..config import Settings, load_clients
from ..meta_api import MetaAPI
from . import auth, views
from .data import DashboardData
from .dates import Period
from .demo import DemoMetaAPI, demo_clients


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


class DashboardConfig:
    def __init__(self, password: str | None, demo: bool, cache_seconds: int = 300,
                 secret: str | None = None, access_token: str = "",
                 api_version: str = "v23.0"):
        self.password = password or None
        self.demo = demo
        self.cache_seconds = cache_seconds
        self.secret = secret or None
        self.access_token = access_token
        self.api_version = api_version

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        s = Settings.from_env()
        return cls(
            password=os.getenv("DASHBOARD_PASSWORD", "").strip(),
            demo=_truthy(os.getenv("DASHBOARD_DEMO")) or not s.access_token,
            cache_seconds=int(os.getenv("DASHBOARD_CACHE_SECONDS", "300") or 300),
            secret=os.getenv("DASHBOARD_SECRET", "").strip(),
            access_token=s.access_token,
            api_version=s.api_version,
        )

    @property
    def login_needed(self) -> bool:
        # Real data always needs a password. Demo data only if you set one.
        return bool(self.password) or not self.demo

    def clients(self):
        clients = load_clients()
        if self.demo and not clients:
            return demo_clients()
        return clients


def create_dashboard_app(config: DashboardConfig | None = None, api=None) -> Starlette:
    cfg = config or DashboardConfig.from_env()
    if api is None:
        api = DemoMetaAPI() if cfg.demo else MetaAPI(cfg.access_token, cfg.api_version)
    data = DashboardData(api, cache_seconds=cfg.cache_seconds)

    def html(body: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(body, status_code=status, headers={
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        })

    def logged_in(request: Request) -> bool:
        if not cfg.password:
            return False
        return auth.check_cookie(request.cookies.get(auth.COOKIE), cfg.password, cfg.secret)

    def gate(request: Request) -> Response | None:
        """Return a response if the visitor may NOT see the page."""
        if not cfg.login_needed:
            return None
        if not cfg.password:
            return html(views.message_page(
                "Password not set",
                "Set <code>DASHBOARD_PASSWORD</code> in your environment (Render → Environment) "
                "and restart. The dashboard shows real client data, so it needs a password."),
                status=503)
        if not logged_in(request):
            return RedirectResponse("/dashboard/login", status_code=303)
        return None

    def period_from(request: Request) -> Period | Response:
        q = request.query_params
        try:
            return Period(q.get("preset"), q.get("since"), q.get("until"))
        except ValueError as e:
            return html(views.message_page("Wrong date", str(e), demo=cfg.demo,
                                           logged_in=logged_in(request)), status=400)

    async def overview(request: Request):
        if (r := gate(request)) is not None:
            return r
        period = period_from(request)
        if isinstance(period, Response):
            return period
        refresh = request.query_params.get("refresh") == "1"
        result = await run_in_threadpool(data.overview, cfg.clients(), period, refresh)
        return html(views.overview_page(result, period, demo=cfg.demo,
                                        logged_in=logged_in(request),
                                        cache_minutes=max(1, cfg.cache_seconds // 60)))

    async def client(request: Request):
        if (r := gate(request)) is not None:
            return r
        period = period_from(request)
        if isinstance(period, Response):
            return period
        key = request.path_params["key"].lower()
        c = cfg.clients().get(key)
        if not c:
            return html(views.message_page("Client not found",
                                           "This client is not in your client list.",
                                           demo=cfg.demo, logged_in=logged_in(request)),
                        status=404)
        refresh = request.query_params.get("refresh") == "1"
        d = await run_in_threadpool(data.client_detail, c, period, refresh)
        return html(views.client_page(c, d, period, demo=cfg.demo,
                                      logged_in=logged_in(request)))

    async def login(request: Request):
        if not cfg.password:
            return RedirectResponse("/dashboard", status_code=303)
        if request.method == "GET":
            if logged_in(request):
                return RedirectResponse("/dashboard", status_code=303)
            return html(views.login_page(demo=cfg.demo))
        body = (await request.body()).decode("utf-8", "replace")
        given = parse_qs(body).get("password", [""])[0]
        if not auth.check_password(given, cfg.password):
            await asyncio.sleep(1)  # slow down password guessing
            return html(views.login_page("Wrong password. Try again.", demo=cfg.demo), status=401)
        resp = RedirectResponse("/dashboard", status_code=303)
        secure = request.url.scheme == "https" or \
            request.headers.get("x-forwarded-proto", "").startswith("https")
        resp.set_cookie(auth.COOKIE, auth.make_cookie(cfg.password, cfg.secret),
                        max_age=auth.SESSION_SECONDS, httponly=True, samesite="lax",
                        secure=secure, path="/dashboard")
        return resp

    async def logout(request: Request):
        resp = RedirectResponse("/dashboard/login", status_code=303)
        resp.delete_cookie(auth.COOKIE, path="/dashboard")
        return resp

    async def to_overview(request: Request):
        return RedirectResponse("/dashboard", status_code=307)

    return Starlette(routes=[
        Route("/dashboard", overview),
        Route("/dashboard/", to_overview),
        Route("/dashboard/client/{key}", client),
        Route("/dashboard/login", login, methods=["GET", "POST"]),
        Route("/dashboard/logout", logout, methods=["POST"]),
    ])
