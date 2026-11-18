"""Facebook Ads MCP server.

Talks directly to graph.facebook.com with your own System User token.
Every write tool (create / update / pause / activate) does NOTHING unless you
pass confirm=true. Without it you only get a preview.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import Client, Settings, load_clients, normalize_account_id
from .insights import INSIGHT_FIELDS, date_params, summarize_row, total_of
from .meta_api import MetaAPI, MetaAPIError

# Meta stores money in "minor units". For most currencies that is cents (x100).
# These currencies have no cents, so the factor is 1.
ZERO_DECIMAL_CURRENCIES = {
    "CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND",
}

INSTRUCTIONS = """\
Manage Facebook / Instagram ads for an agency's clients via the Meta Marketing API.
Start with list_clients to see client names. Use the client name (key) in other tools.
Money values are in the ad account's currency (e.g. 25 means 25 USD / 25 INR), not cents.
Write tools (create_*, update_budget, set_status) only make changes when confirm=true.
Always call them first with confirm=false, show the preview to the user, and only
repeat with confirm=true after the user clearly says yes. New campaigns, ad sets
and ads are always created PAUSED.
"""

settings = Settings.from_env()

_host = os.getenv("HOST", "127.0.0.1")
_port = int(os.getenv("PORT", "8000"))

mcp = FastMCP(
    "facebook-ads",
    instructions=INSTRUCTIONS,
    host=_host,
    port=_port,
    stateless_http=True,
    # We protect the HTTP endpoint with our own secret key (see app.py),
    # so the built-in Host check is turned off to work behind Render/Railway.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_api: MetaAPI | None = None


def api() -> MetaAPI:
    global _api
    if _api is None:
        _api = MetaAPI(settings.access_token, settings.api_version)
    return _api


def clients() -> dict[str, Client]:
    # Read every time, so editing clients.json needs no restart.
    return load_clients()


def safe(fn):
    """Return a clear error dict instead of crashing the tool."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (MetaAPIError, ValueError, PermissionError) as e:
            return {"ok": False, "error": str(e)}

    return wrapper


def get_client(name: str) -> Client:
    all_clients = clients()
    key = (name or "").strip().lower()
    if key in all_clients:
        return all_clients[key]
    for c in all_clients.values():
        if c.name.lower() == key or c.ad_account_id == normalize_account_id(key):
            return c
    if settings.allow_unknown_accounts and key.replace("act_", "").isdigit():
        return Client(key=key, name=key, ad_account_id=normalize_account_id(key))
    known = ", ".join(sorted(all_clients)) or "(none - fill clients.json)"
    raise ValueError(f"Unknown client '{name}'. Known clients: {known}")


def check_owner(client: Client, object_id: str) -> None:
    """Make sure a campaign / ad set / ad really belongs to this client."""
    owner = api().object_account(object_id)
    if owner != client.ad_account_id:
        raise PermissionError(
            f"Object {object_id} belongs to {owner}, not to client "
            f"'{client.key}' ({client.ad_account_id}). Nothing was changed."
        )


def currency_factor(client: Client) -> tuple[str, int]:
    cur = api().account_info(client.ad_account_id).get("currency", "USD")
    return cur, (1 if cur in ZERO_DECIMAL_CURRENCIES else 100)


def check_budget(client: Client, daily: float | None, lifetime: float | None) -> None:
    max_daily = client.max_daily_budget or settings.global_max_daily_budget
    max_life = client.max_lifetime_budget or settings.global_max_lifetime_budget
    if daily is not None:
        if daily <= 0:
            raise ValueError("daily_budget must be more than 0.")
        if max_daily is not None and daily > max_daily:
            raise PermissionError(
                f"Daily budget {daily} is above the limit {max_daily} for "
                f"'{client.key}'. Change max_daily_budget in clients.json to allow it."
            )
    if lifetime is not None:
        if lifetime <= 0:
            raise ValueError("lifetime_budget must be more than 0.")
        if max_life is not None and lifetime > max_life:
            raise PermissionError(
                f"Lifetime budget {lifetime} is above the limit {max_life} for "
                f"'{client.key}'. Change max_lifetime_budget in clients.json to allow it."
            )


def preview(action: str, client: Client, payload: dict) -> dict:
    return {
        "ok": True,
        "preview": True,
        "action": action,
        "client": client.key,
        "ad_account_id": client.ad_account_id,
        "will_send": payload,
        "message": "Nothing was changed yet. Show this to the user. If they agree, "
                   "call the same tool again with confirm=true.",
    }


def _money_fields(obj: dict, factor: int) -> dict:
    for k in ("daily_budget", "lifetime_budget", "budget_remaining", "bid_amount"):
        if obj.get(k) not in (None, ""):
            obj[k] = round(float(obj[k]) / factor, 2)
    return obj


# ---------------------------------------------------------------- read tools


@mcp.tool()
@safe
def list_clients() -> dict:
    """List all clients from the config (name, ad account, page, budget limits)."""
    cl = clients()
    return {"ok": True, "count": len(cl), "clients": [c.public() for c in cl.values()]}


@mcp.tool()
@safe
def discover_ad_accounts() -> dict:
    """List every ad account the access token can see. Use it to fill clients.json."""
    rows = api().my_ad_accounts()
    status = {1: "ACTIVE", 2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW",
              9: "IN_GRACE_PERIOD", 101: "CLOSED"}
    configured = {c.ad_account_id for c in clients().values()}
    return {"ok": True, "count": len(rows), "ad_accounts": [{
        "ad_account_id": r["id"],
        "name": r.get("name"),
        "currency": r.get("currency"),
        "status": status.get(r.get("account_status"), r.get("account_status")),
        "business": (r.get("business") or {}).get("name"),
        "in_clients_json": r["id"] in configured,
    } for r in rows]}


@mcp.tool()
@safe
def discover_pages() -> dict:
    """List the Facebook Pages the access token can see (id and name)."""
    rows = api().get_all("me/accounts", {"fields": "id,name,category"}, limit=500)
    return {"ok": True, "count": len(rows), "pages": rows}


@mcp.tool()
@safe
def get_insights(
    client: str,
    date_preset: str = "last_7d",
    since: str | None = None,
    until: str | None = None,
    level: Literal["account", "campaign", "adset", "ad"] = "account",
    daily_breakdown: bool = False,
    limit: int = 100,
) -> dict:
    """Get results for ONE client: spend, impressions, clicks, CPC, CTR, leads, CPL,
    purchases, ROAS.

    date_preset: today, yesterday, last_7d, last_14d, last_30d, this_month,
    last_month, maximum ... OR give since + until as YYYY-MM-DD.
    level: account (one total), campaign, adset or ad (one row each).
    daily_breakdown: true = one row per day.
    """
    c = get_client(client)
    params: dict[str, Any] = {"fields": ",".join(INSIGHT_FIELDS), "level": level}
    params.update(date_params(date_preset, since, until))
    if daily_breakdown:
        params["time_increment"] = 1
    rows = [summarize_row(r) for r in api().get_all(f"{c.ad_account_id}/insights",
                                                    params, limit=limit)]
    currency = rows[0].get("account_currency") if rows else None
    return {
        "ok": True,
        "client": c.key,
        "ad_account_id": c.ad_account_id,
        "currency": currency,
        "period": params.get("date_preset") or params.get("time_range"),
        "total": total_of(rows),
        "rows": rows if (level != "account" or daily_breakdown) else [],
    }


@mcp.tool()
@safe
def get_all_clients_insights(
    date_preset: str = "last_7d",
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """Get one summary line per client (spend, leads, CPL, CPC, ROAS) for all clients.
    Good for a daily or weekly agency report."""
    period = date_params(date_preset, since, until)
    out, errors = [], []
    for c in clients().values():
        try:
            params = {"fields": ",".join(INSIGHT_FIELDS), "level": "account", **period}
            rows = api().get_all(f"{c.ad_account_id}/insights", params, limit=5)
            s = summarize_row(rows[0]) if rows else summarize_row({})
            s.update({"client": c.key, "name": c.name, "ad_account_id": c.ad_account_id})
            s.pop("account_name", None)
            out.append(s)
        except MetaAPIError as e:
            errors.append({"client": c.key, "error": str(e)})
    out.sort(key=lambda r: r["spend"], reverse=True)
    by_currency: dict[str, list] = {}
    for r in out:
        by_currency.setdefault(r.get("account_currency") or "UNKNOWN", []).append(r)
    return {
        "ok": True,
        "period": period,
        "clients": out,
        "totals_by_currency": {cur: total_of(rs) for cur, rs in by_currency.items()},
        "errors": errors,
    }


@mcp.tool()
@safe
def list_campaigns(client: str, status: Literal["ALL", "ACTIVE", "PAUSED"] = "ALL",
                   limit: int = 100) -> dict:
    """List campaigns of a client with status, objective and budget."""
    c = get_client(client)
    cur, factor = currency_factor(c)
    params: dict[str, Any] = {"fields": "id,name,status,effective_status,objective,"
                              "daily_budget,lifetime_budget,budget_remaining,"
                              "bid_strategy,created_time,start_time,stop_time"}
    if status != "ALL":
        params["effective_status"] = [status]
    rows = [_money_fields(r, factor) for r in
            api().get_all(f"{c.ad_account_id}/campaigns", params, limit=limit)]
    return {"ok": True, "client": c.key, "currency": cur, "count": len(rows), "campaigns": rows}


@mcp.tool()
@safe
def list_adsets(client: str, campaign_id: str | None = None,
                status: Literal["ALL", "ACTIVE", "PAUSED"] = "ALL", limit: int = 100) -> dict:
    """List ad sets of a client (optionally only inside one campaign)."""
    c = get_client(client)
    cur, factor = currency_factor(c)
    parent = campaign_id or c.ad_account_id
    if campaign_id:
        check_owner(c, campaign_id)
    params: dict[str, Any] = {"fields": "id,name,campaign_id,status,effective_status,"
                              "daily_budget,lifetime_budget,budget_remaining,"
                              "optimization_goal,billing_event,bid_strategy,bid_amount,"
                              "start_time,end_time,targeting"}
    if status != "ALL":
        params["effective_status"] = [status]
    rows = [_money_fields(r, factor) for r in
            api().get_all(f"{parent}/adsets", params, limit=limit)]
    return {"ok": True, "client": c.key, "currency": cur, "count": len(rows), "adsets": rows}


@mcp.tool()
@safe
def list_ads(client: str, adset_id: str | None = None, campaign_id: str | None = None,
             status: Literal["ALL", "ACTIVE", "PAUSED"] = "ALL", limit: int = 100) -> dict:
    """List ads of a client (optionally only inside one ad set or campaign)."""
    c = get_client(client)
    parent = adset_id or campaign_id or c.ad_account_id
    if parent != c.ad_account_id:
        check_owner(c, parent)
    params: dict[str, Any] = {"fields": "id,name,adset_id,campaign_id,status,"
                              "effective_status,creative{id,name,title,body,"
                              "thumbnail_url,object_story_spec},created_time"}
    if status != "ALL":
        params["effective_status"] = [status]
    rows = api().get_all(f"{parent}/ads", params, limit=limit)
    return {"ok": True, "client": c.key, "count": len(rows), "ads": rows}


@mcp.tool()
@safe
def get_page_insights(
    client: str,
    metrics: str = "page_post_engagements,page_daily_follows_unique,page_media_view",
    period: Literal["day", "week", "days_28"] = "day",
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """Read Facebook Page numbers for a client's Page (followers + Page insights).

    metrics: comma separated Page insight metric names. Meta changes these names
    sometimes; if one fails, the error says which. since/until: YYYY-MM-DD.
    """
    c = get_client(client)
    if not c.page_id:
        raise ValueError(f"Client '{c.key}' has no page_id in clients.json.")
    token = api().page_token(c.page_id)
    info = api().get(c.page_id, {"fields": "id,name,fan_count,followers_count,link"},
                     token=token)
    params: dict[str, Any] = {"metric": metrics, "period": period}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    result: dict[str, Any] = {"ok": True, "client": c.key, "page": info, "metrics": {}}
    try:
        data = api().get(f"{c.page_id}/insights", params, token=token).get("data", [])
        for m in data:
            result["metrics"][m["name"]] = [
                {"date": v.get("end_time", "")[:10], "value": v.get("value")}
                for v in m.get("values", [])
            ]
    except MetaAPIError as e:
        result["metrics_error"] = str(e)
    return result


@mcp.tool()
@safe
def list_lead_forms(client: str) -> dict:
    """List Instant Forms (lead forms) on the client's Page. Needed for lead ads."""
    c = get_client(client)
    if not c.page_id:
        raise ValueError(f"Client '{c.key}' has no page_id in clients.json.")
    token = api().page_token(c.page_id)
    rows = api().get(f"{c.page_id}/leadgen_forms",
                     {"fields": "id,name,status,leads_count,created_time", "limit": 100},
                     token=token).get("data", [])
    return {"ok": True, "client": c.key, "count": len(rows), "forms": rows}


# --------------------------------------------------------------- write tools


@mcp.tool()
@safe
def create_campaign(
    client: str,
    name: str,
    objective: Literal["OUTCOME_LEADS", "OUTCOME_SALES", "OUTCOME_TRAFFIC",
                       "OUTCOME_ENGAGEMENT", "OUTCOME_AWARENESS",
                       "OUTCOME_APP_PROMOTION"] = "OUTCOME_LEADS",
    daily_budget: float | None = None,
    lifetime_budget: float | None = None,
    special_ad_categories: list[str] | None = None,
    bid_strategy: Literal["LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP",
                          "COST_CAP"] | None = None,
    confirm: bool = False,
) -> dict:
    """Create a new campaign (always PAUSED).

    Give daily_budget OR lifetime_budget only if you want the budget on the
    campaign (Advantage campaign budget). Otherwise set budget on the ad set.
    special_ad_categories: e.g. ["HOUSING"], ["EMPLOYMENT"], ["FINANCIAL_PRODUCTS_SERVICES"].
    confirm=false only shows a preview.
    """
    c = get_client(client)
    check_budget(c, daily_budget, lifetime_budget)
    payload: dict[str, Any] = {
        "name": name,
        "objective": objective,
        "status": "PAUSED",
        "special_ad_categories": special_ad_categories or [],
    }
    if daily_budget or lifetime_budget:
        cur, factor = currency_factor(c)
        if daily_budget:
            payload["daily_budget"] = int(round(daily_budget * factor))
        if lifetime_budget:
            payload["lifetime_budget"] = int(round(lifetime_budget * factor))
        payload["bid_strategy"] = bid_strategy or "LOWEST_COST_WITHOUT_CAP"
    else:
        payload["is_adset_budget_sharing_enabled"] = False
        if bid_strategy:
            payload["bid_strategy"] = bid_strategy
    if not confirm:
        return preview("create_campaign", c, payload)
    res = api().post(f"{c.ad_account_id}/campaigns", payload)
    return {"ok": True, "created": "campaign", "id": res.get("id"), "status": "PAUSED",
            "client": c.key}


@mcp.tool()
@safe
def create_adset(
    client: str,
    campaign_id: str,
    name: str,
    optimization_goal: str = "LEAD_GENERATION",
    billing_event: str = "IMPRESSIONS",
    daily_budget: float | None = None,
    lifetime_budget: float | None = None,
    countries: list[str] | None = None,
    age_min: int = 18,
    age_max: int = 65,
    genders: list[int] | None = None,
    targeting: dict | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    destination_type: str | None = None,
    use_page_as_promoted_object: bool = True,
    promoted_object: dict | None = None,
    bid_strategy: str | None = None,
    bid_amount: float | None = None,
    confirm: bool = False,
) -> dict:
    """Create a new ad set inside a campaign (always PAUSED).

    optimization_goal: LEAD_GENERATION, LINK_CLICKS, LANDING_PAGE_VIEWS,
    OFFSITE_CONVERSIONS, CONVERSATIONS, REACH, IMPRESSIONS, POST_ENGAGEMENT ...
    Simple targeting: countries (e.g. ["IN"]), age_min, age_max, genders ([1]=men, [2]=women).
    Or pass a full Meta `targeting` dict (it replaces the simple fields).
    destination_type: e.g. ON_AD (instant form), WEBSITE, MESSENGER, WHATSAPP.
    Budget is not needed if the campaign already has a campaign budget.
    start_time / end_time: ISO time like 2026-12-01T09:00:00+0530 (lifetime budget needs end_time).
    confirm=false only shows a preview.
    """
    c = get_client(client)
    check_owner(c, campaign_id)
    check_budget(c, daily_budget, lifetime_budget)
    tgt = targeting or {
        "geo_locations": {"countries": countries or ["IN"]},
        "age_min": age_min,
        "age_max": age_max,
        **({"genders": genders} if genders else {}),
    }
    payload: dict[str, Any] = {
        "name": name,
        "campaign_id": campaign_id,
        "optimization_goal": optimization_goal,
        "billing_event": billing_event,
        "targeting": tgt,
        "status": "PAUSED",
    }
    factor = None
    if daily_budget or lifetime_budget or bid_amount:
        _, factor = currency_factor(c)
    if daily_budget:
        payload["daily_budget"] = int(round(daily_budget * factor))
    if lifetime_budget:
        payload["lifetime_budget"] = int(round(lifetime_budget * factor))
    if daily_budget or lifetime_budget:
        payload["bid_strategy"] = bid_strategy or "LOWEST_COST_WITHOUT_CAP"
    elif bid_strategy:
        payload["bid_strategy"] = bid_strategy
    if bid_amount:
        payload["bid_amount"] = int(round(bid_amount * factor))
    if start_time:
        payload["start_time"] = start_time
    if end_time:
        payload["end_time"] = end_time
    if destination_type:
        payload["destination_type"] = destination_type
    if promoted_object:
        payload["promoted_object"] = promoted_object
    elif use_page_as_promoted_object and c.page_id and optimization_goal in (
            "LEAD_GENERATION", "QUALITY_LEAD", "CONVERSATIONS", "PAGE_LIKES"):
        payload["promoted_object"] = {"page_id": c.page_id}
    if not confirm:
        return preview("create_adset", c, payload)
    res = api().post(f"{c.ad_account_id}/adsets", payload)
    return {"ok": True, "created": "adset", "id": res.get("id"), "status": "PAUSED",
            "client": c.key}


@mcp.tool()
@safe
def create_ad(
    client: str,
    adset_id: str,
    name: str,
    message: str | None = None,
    link: str | None = None,
    headline: str | None = None,
    description: str | None = None,
    image_url: str | None = None,
    image_hash: str | None = None,
    call_to_action: str = "LEARN_MORE",
    lead_form_id: str | None = None,
    existing_post_id: str | None = None,
    instagram_user_id: str | None = None,
    confirm: bool = False,
) -> dict:
    """Create a new ad inside an ad set (always PAUSED).

    Option A - new image ad: message (main text), link (website), headline,
    description, image_url (public link to a JPG/PNG) or image_hash,
    call_to_action (LEARN_MORE, SIGN_UP, SHOP_NOW, CONTACT_US, BOOK_NOW, APPLY_NOW,
    GET_QUOTE, WHATSAPP_MESSAGE, ...). For lead ads add lead_form_id
    (see list_lead_forms); link can then be any website of the client.
    Option B - use an existing Page post: existing_post_id ("pageid_postid").
    confirm=false only shows a preview (image is not uploaded in preview).
    """
    c = get_client(client)
    check_owner(c, adset_id)
    if existing_post_id:
        creative: dict[str, Any] = {"name": f"{name} creative", "object_story_id": existing_post_id}
    else:
        if not c.page_id:
            raise ValueError(f"Client '{c.key}' has no page_id in clients.json.")
        if not link:
            raise ValueError("'link' is needed for a new ad (website URL).")
        link_data: dict[str, Any] = {"link": link}
        if message:
            link_data["message"] = message
        if headline:
            link_data["name"] = headline
        if description:
            link_data["description"] = description
        cta: dict[str, Any] = {"type": call_to_action, "value": {"link": link}}
        if lead_form_id:
            cta["value"]["lead_gen_form_id"] = lead_form_id
        link_data["call_to_action"] = cta
        if image_hash:
            link_data["image_hash"] = image_hash
        story: dict[str, Any] = {"page_id": c.page_id, "link_data": link_data}
        if instagram_user_id:
            story["instagram_user_id"] = instagram_user_id
        creative = {"name": f"{name} creative", "object_story_spec": story}

    ad_payload = {"name": name, "adset_id": adset_id, "status": "PAUSED"}
    if not confirm:
        return preview("create_ad", c, {
            "creative": creative,
            "image_to_upload": image_url if (image_url and not image_hash) else None,
            "ad": ad_payload,
        })

    if image_url and not image_hash and not existing_post_id:
        h = api().upload_image_from_url(c.ad_account_id, image_url)
        creative["object_story_spec"]["link_data"]["image_hash"] = h
    cr = api().post(f"{c.ad_account_id}/adcreatives", creative)
    ad = api().post(f"{c.ad_account_id}/ads", {**ad_payload,
                                               "creative": {"creative_id": cr["id"]}})
    return {"ok": True, "created": "ad", "id": ad.get("id"), "creative_id": cr.get("id"),
            "status": "PAUSED", "client": c.key}


@mcp.tool()
@safe
def update_budget(
    client: str,
    object_id: str,
    daily_budget: float | None = None,
    lifetime_budget: float | None = None,
    confirm: bool = False,
) -> dict:
    """Change the budget of a campaign or ad set (amount in account currency).
    Checks the client's max budget limit. confirm=false only shows a preview."""
    c = get_client(client)
    if daily_budget is None and lifetime_budget is None:
        raise ValueError("Give daily_budget or lifetime_budget.")
    check_owner(c, object_id)
    check_budget(c, daily_budget, lifetime_budget)
    cur, factor = currency_factor(c)
    before = _money_fields(api().get(object_id, {"fields": "name,daily_budget,lifetime_budget"}),
                           factor)
    payload: dict[str, Any] = {}
    if daily_budget is not None:
        payload["daily_budget"] = int(round(daily_budget * factor))
    if lifetime_budget is not None:
        payload["lifetime_budget"] = int(round(lifetime_budget * factor))
    if not confirm:
        p = preview("update_budget", c, {"object_id": object_id, **payload})
        p.update({"currency": cur, "current": before,
                  "new": {"daily_budget": daily_budget, "lifetime_budget": lifetime_budget}})
        return p
    api().post(object_id, payload)
    return {"ok": True, "updated": object_id, "name": before.get("name"), "currency": cur,
            "before": before,
            "after": {"daily_budget": daily_budget, "lifetime_budget": lifetime_budget}}


@mcp.tool()
@safe
def set_status(
    client: str,
    object_id: str,
    status: Literal["ACTIVE", "PAUSED"],
    confirm: bool = False,
) -> dict:
    """Pause or activate a campaign, ad set or ad. ACTIVE starts spending money.
    confirm=false only shows a preview."""
    c = get_client(client)
    check_owner(c, object_id)
    before = api().get(object_id, {"fields": "name,status,effective_status"})
    if not confirm:
        p = preview("set_status", c, {"object_id": object_id, "status": status})
        p["current"] = before
        return p
    api().post(object_id, {"status": status})
    return {"ok": True, "object_id": object_id, "name": before.get("name"),
            "old_status": before.get("status"), "new_status": status}
