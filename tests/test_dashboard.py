"""Offline tests for the dashboard website. No real Meta calls."""

from starlette.testclient import TestClient

from fb_ads_mcp.dashboard import DashboardConfig, create_dashboard_app
from fb_ads_mcp.dashboard.dates import Period
from fb_ads_mcp.dashboard.demo import DemoMetaAPI
from fb_ads_mcp.dashboard.views import fmt_money


def demo_app(password=None):
    return create_dashboard_app(DashboardConfig(password=password, demo=True))


def test_demo_overview_and_client_page(monkeypatch):
    monkeypatch.delenv("CLIENTS_JSON", raising=False)
    monkeypatch.setenv("CLIENTS_FILE", "does-not-exist.json")
    c = TestClient(demo_app())
    r = c.get("/dashboard?preset=last_30d")
    assert r.status_code == 200
    assert "DEMO DATA" in r.text and "Smile Dental Clinic" in r.text and "CPL" in r.text
    r = c.get("/dashboard/client/smile_dental?since=2026-10-01&until=2026-10-31")
    assert r.status_code == 200 and "Spend per day" in r.text and "Campaigns" in r.text
    assert c.get("/dashboard/client/nobody").status_code == 404
    assert c.get("/dashboard?since=2026-10-01").status_code == 400


def test_real_data_needs_password():
    app = create_dashboard_app(DashboardConfig(password=None, demo=False, access_token="x"),
                               api=DemoMetaAPI())
    r = TestClient(app).get("/dashboard")
    assert r.status_code == 503 and "DASHBOARD_PASSWORD" in r.text


def test_login(monkeypatch):
    monkeypatch.setenv("CLIENTS_FILE", "does-not-exist.json")
    monkeypatch.delenv("CLIENTS_JSON", raising=False)
    app = create_dashboard_app(DashboardConfig(password="pw123", demo=False, access_token="x"),
                               api=DemoMetaAPI())
    c = TestClient(app, base_url="https://testserver")
    r = c.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard/login"
    r = c.post("/dashboard/login", content="password=wrong",
               headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 401
    r = c.post("/dashboard/login", content="password=pw123",
               headers={"Content-Type": "application/x-www-form-urlencoded"},
               follow_redirects=False)
    assert r.status_code == 303 and "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/dashboard").status_code == 200
    c.cookies.set("fbdash_session", "9999999999.bad", path="/dashboard")
    assert c.get("/dashboard", follow_redirects=False).status_code == 303


def test_totals_use_existing_insights_math():
    from fb_ads_mcp.config import Client
    from fb_ads_mcp.dashboard.data import DashboardData

    d = DashboardData(DemoMetaAPI())
    c = Client(key="a", name="A", ad_account_id="act_1")
    detail = d.client_detail(c, Period("last_7d"))
    t = detail["total"]
    assert detail["currency"] == "INR" and len(detail["daily"]) == 7
    assert t["cpl"] == round(t["spend"] / t["leads"], 2)
    assert abs(sum(r["spend"] for r in detail["campaigns"]) - t["spend"]) < 1


def test_long_range_is_monthly():
    assert Period("maximum").time_increment() == "monthly"
    assert Period("last_30d").time_increment() == 1


def test_money_format():
    assert fmt_money(1234567, "INR") == "₹12,34,567"
    assert fmt_money(99.999, "USD") == "$100.00"
    assert fmt_money(None, "INR") == "—"


def test_combined_server_routes(monkeypatch):
    from fb_ads_mcp.__main__ import build_http_app

    # No "with": the MCP session manager may only start once per test run.
    c = TestClient(build_http_app())
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/dashboard"
    assert "Ads Dashboard" in c.get("/dashboard").text
    # /mcp still needs the secret key
    assert c.post("/mcp", json={}).status_code == 401
