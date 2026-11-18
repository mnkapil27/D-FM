"""Turn raw Meta insights rows into simple numbers: spend, leads, CPL, CPC, ROAS."""

from __future__ import annotations

INSIGHT_FIELDS = [
    "account_id", "account_name", "account_currency",
    "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
    "spend", "impressions", "reach", "frequency", "clicks", "inline_link_clicks",
    "cpc", "cpm", "ctr", "actions", "action_values", "purchase_roas",
    "date_start", "date_stop",
]

LEAD_TYPES = [
    "lead",
    "onsite_conversion.lead_grouped",
    "offsite_conversion.fb_pixel_lead",
    "leadgen_grouped",
]
PURCHASE_TYPES = [
    "omni_purchase",
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_web_purchase",
]
MESSAGE_TYPES = ["onsite_conversion.messaging_conversation_started_7d"]

DATE_PRESETS = [
    "today", "yesterday", "this_week_mon_today", "last_week_mon_sun", "last_3d",
    "last_7d", "last_14d", "last_28d", "last_30d", "last_90d", "this_month",
    "last_month", "this_quarter", "last_quarter", "this_year", "last_year", "maximum",
]


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _pick(action_list: list[dict] | None, types: list[str]) -> float:
    if not action_list:
        return 0.0
    by_type = {a.get("action_type"): _f(a.get("value")) for a in action_list}
    for t in types:
        if t in by_type:
            return by_type[t]
    return 0.0


def _div(a: float, b: float) -> float | None:
    return round(a / b, 2) if b else None


def summarize_row(row: dict) -> dict:
    spend = _f(row.get("spend"))
    clicks = _f(row.get("clicks"))
    link_clicks = _f(row.get("inline_link_clicks"))
    impressions = _f(row.get("impressions"))
    leads = _pick(row.get("actions"), LEAD_TYPES)
    purchases = _pick(row.get("actions"), PURCHASE_TYPES)
    messages = _pick(row.get("actions"), MESSAGE_TYPES)
    revenue = _pick(row.get("action_values"), PURCHASE_TYPES)
    roas = _div(revenue, spend)
    if roas is None and row.get("purchase_roas"):
        roas = round(_pick(row.get("purchase_roas"), PURCHASE_TYPES), 2) or None

    out = {k: row[k] for k in (
        "account_name", "campaign_id", "campaign_name", "adset_id", "adset_name",
        "ad_id", "ad_name", "date_start", "date_stop", "account_currency",
    ) if row.get(k)}
    out.update({
        "spend": round(spend, 2),
        "impressions": int(impressions),
        "reach": int(_f(row.get("reach"))),
        "clicks": int(clicks),
        "link_clicks": int(link_clicks),
        "ctr_percent": round(_f(row.get("ctr")), 2),
        "cpc": _div(spend, clicks),
        "cpm": _div(spend * 1000, impressions),
        "leads": int(leads),
        "cpl": _div(spend, leads),
        "messages_started": int(messages),
        "purchases": int(purchases),
        "purchase_value": round(revenue, 2),
        "roas": roas,
    })
    return out


def total_of(rows: list[dict]) -> dict:
    """Add up summarized rows (same currency) and recompute the ratios."""
    t = {k: 0.0 for k in ("spend", "impressions", "clicks", "link_clicks", "leads",
                          "purchases", "purchase_value", "messages_started")}
    for r in rows:
        for k in t:
            t[k] += r.get(k) or 0
    t["spend"] = round(t["spend"], 2)
    t["purchase_value"] = round(t["purchase_value"], 2)
    for k in ("impressions", "clicks", "link_clicks", "leads", "purchases", "messages_started"):
        t[k] = int(t[k])
    t["cpc"] = _div(t["spend"], t["clicks"])
    t["cpl"] = _div(t["spend"], t["leads"])
    t["roas"] = _div(t["purchase_value"], t["spend"])
    return t


def date_params(date_preset: str | None, since: str | None, until: str | None) -> dict:
    if since or until:
        if not (since and until):
            raise ValueError("Give both 'since' and 'until' (format YYYY-MM-DD).")
        return {"time_range": {"since": since, "until": until}}
    preset = date_preset or "last_7d"
    if preset not in DATE_PRESETS:
        raise ValueError(f"Unknown date_preset '{preset}'. Use one of: {', '.join(DATE_PRESETS)}")
    return {"date_preset": preset}
