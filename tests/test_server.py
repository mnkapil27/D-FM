"""Offline tests. No real Meta calls: the API is replaced by a fake."""

import json
import os

os.environ["CLIENTS_JSON"] = json.dumps({"clients": {
    "pizza": {"name": "Pizza Hub", "ad_account_id": "111", "page_id": "999",
              "max_daily_budget": 50},
}})
os.environ.setdefault("META_ACCESS_TOKEN", "test-token")
os.environ.setdefault("MCP_AUTH_TOKEN", "secret123")

import pytest  # noqa: E402

from fb_ads_mcp import server  # noqa: E402
from fb_ads_mcp.insights import summarize_row  # noqa: E402


class FakeAPI:
    def __init__(self):
        self.posts = []

    def account_info(self, acc):
        return {"currency": "USD"}

    def object_account(self, oid):
        return "act_111" if oid.startswith("good") else "act_222"

    def get(self, path, params=None, token=None):
        return {"name": "Thing", "daily_budget": "2000", "status": "PAUSED"}

    def post(self, path, data=None):
        self.posts.append((path, data))
        return {"id": "new_1", "success": True}

    def get_all(self, path, params=None, limit=200):
        return [{"spend": "100", "clicks": "50", "impressions": "10000",
                 "actions": [{"action_type": "lead", "value": "20"}],
                 "action_values": [{"action_type": "omni_purchase", "value": "400"}],
                 "account_currency": "USD"}]


@pytest.fixture
def fake(monkeypatch):
    f = FakeAPI()
    monkeypatch.setattr(server, "_api", f)
    return f


def test_summarize_row():
    s = summarize_row({"spend": "100", "clicks": "40", "impressions": "8000",
                       "actions": [{"action_type": "lead", "value": "10"}],
                       "action_values": [{"action_type": "omni_purchase", "value": "300"}]})
    assert s["cpl"] == 10.0 and s["cpc"] == 2.5 and s["roas"] == 3.0 and s["leads"] == 10


def test_list_clients():
    r = server.list_clients()
    assert r["clients"][0]["ad_account_id"] == "act_111"


def test_insights(fake):
    r = server.get_insights("pizza")
    assert r["total"]["cpl"] == 5.0 and r["total"]["roas"] == 4.0


def test_unknown_client(fake):
    assert server.get_insights("nobody")["ok"] is False


def test_create_needs_confirm(fake):
    r = server.create_campaign("pizza", "Test", daily_budget=20)
    assert r["preview"] is True and fake.posts == []
    assert r["will_send"]["status"] == "PAUSED"
    assert r["will_send"]["daily_budget"] == 2000  # 20 USD -> 2000 cents
    r = server.create_campaign("pizza", "Test", daily_budget=20, confirm=True)
    assert r["ok"] and fake.posts[0][1]["status"] == "PAUSED"


def test_budget_limit(fake):
    r = server.update_budget("pizza", "good_cmp", daily_budget=500, confirm=True)
    assert r["ok"] is False and "limit" in r["error"] and fake.posts == []


def test_owner_check(fake):
    r = server.set_status("pizza", "other_cmp", "ACTIVE", confirm=True)
    assert r["ok"] is False and fake.posts == []
    r = server.set_status("pizza", "good_cmp", "ACTIVE", confirm=True)
    assert r["ok"] and fake.posts == [("good_cmp", {"status": "ACTIVE"})]


def test_adset_always_paused(fake):
    r = server.create_adset("pizza", "good_cmp", "Set 1", daily_budget=10, countries=["IN"])
    assert r["will_send"]["status"] == "PAUSED"
    assert r["will_send"]["promoted_object"] == {"page_id": "999"}


def test_http_auth():
    from starlette.testclient import TestClient
    from fb_ads_mcp.__main__ import build_http_app

    app = build_http_app()
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        hdrs = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"}
        assert c.post("/mcp", json=body, headers=hdrs).status_code == 401
        assert c.post("/mcp?key=wrong", json=body, headers=hdrs).status_code == 401
        ok = c.post("/mcp?key=secret123", json=body, headers=hdrs)
        assert ok.status_code == 200 and "create_campaign" in ok.text
