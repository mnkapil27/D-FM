"""Demo mode: fake numbers that look like real Meta data.

Used when META_ACCESS_TOKEN is empty or DASHBOARD_DEMO=true, so you can see the
dashboard before you add your real token. Nothing here talks to Meta.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from datetime import date, timedelta

from ..config import Client
from .dates import parse_day, resolve_range

DEMO_CLIENTS = {
    "shree_sweets": ("Shree Sweets", "act_100000000000001"),
    "smile_dental": ("Smile Dental Clinic", "act_100000000000002"),
    "patel_realty": ("Patel Real Estate", "act_100000000000003"),
    "urban_fit_gym": ("Urban Fit Gym", "act_100000000000004"),
    "krishna_jewellers": ("Krishna Jewellers", "act_100000000000005"),
    "green_leaf_cafe": ("Green Leaf Cafe", "act_100000000000006"),
}

CAMPAIGN_NAMES = [
    "Lead Form - Ahmedabad", "Lead Form - Surat", "WhatsApp Messages",
    "Diwali Offer", "Retargeting - Website", "Brand Awareness", "Sales - Catalog",
]


def demo_clients() -> dict[str, Client]:
    return {k: Client(key=k, name=n, ad_account_id=a) for k, (n, a) in DEMO_CLIENTS.items()}


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


class DemoMetaAPI:
    """Has the same get_all() / account_info() as MetaAPI, but makes up the numbers."""

    def account_info(self, account_id: str) -> dict:
        return {"id": account_id, "name": account_id, "currency": "INR"}

    # --- the fake "account" ---
    def _profile(self, acc: str) -> dict:
        r = random.Random(_seed("profile", acc))
        n = r.randint(2, 4)
        names = r.sample(CAMPAIGN_NAMES, n)
        return {
            "daily_spend": r.choice([600, 900, 1500, 2500, 4000]),
            "cpl": r.uniform(60, 400),
            "sells": r.random() < 0.4,  # some clients get purchases / ROAS
            "campaigns": [(f"23850{_seed(acc, nm) % 10**10:010d}", nm) for nm in names],
        }

    def _day(self, acc: str, cmp_id: str, share: float, d: date, prof: dict) -> dict:
        r = random.Random(_seed(acc, cmp_id, d.isoformat()))
        weekend = 0.8 if d.weekday() >= 5 else 1.0
        spend = prof["daily_spend"] * share * weekend * r.uniform(0.7, 1.3)
        impressions = spend * r.uniform(55, 90)
        clicks = impressions * r.uniform(0.008, 0.025)
        leads = max(0, round(spend / prof["cpl"] * r.uniform(0.6, 1.4)))
        purchases = round(leads * r.uniform(0.1, 0.3)) if prof["sells"] else 0
        return {"spend": spend, "impressions": impressions, "reach": impressions * 0.7,
                "clicks": clicks, "inline_link_clicks": clicks * 0.8, "leads": leads,
                "purchases": purchases,
                "revenue": spend * r.uniform(2.0, 5.0) if purchases else 0}

    def get_all(self, path: str, params: dict | None = None, limit: int = 200) -> list[dict]:
        params = params or {}
        acc = path.split("/")[0]
        if "time_range" in params:
            tr = params["time_range"]
            since, until = parse_day(tr["since"]), parse_day(tr["until"])
        else:
            since, until = resolve_range(params.get("date_preset", "last_7d"))
        prof = self._profile(acc)
        by_campaign = params.get("level") == "campaign"
        step = params.get("time_increment")

        buckets: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
        spans: dict[tuple, list] = {}
        shares = [1.0 / len(prof["campaigns"])] * len(prof["campaigns"])
        d = since
        while d <= until:
            for (cid, cname), share in zip(prof["campaigns"], shares):
                day = self._day(acc, cid, share, d, prof)
                if step == 1:
                    tkey = (d, d)
                elif step == "monthly":
                    tkey = (d.replace(day=1), None)
                else:
                    tkey = (since, until)
                key = (tkey, (cid, cname) if by_campaign else None)
                for k, v in day.items():
                    buckets[key][k] += v
                span = spans.setdefault(key, [d, d])
                span[1] = d
            d += timedelta(days=1)

        rows = []
        for (tkey, cmp), v in sorted(buckets.items(), key=lambda kv: (kv[0][0][0], str(kv[0][1]))):
            start, stop = spans[(tkey, cmp)]
            row = {
                "account_id": acc.replace("act_", ""), "account_currency": "INR",
                "spend": f"{v['spend']:.2f}", "impressions": str(int(v["impressions"])),
                "reach": str(int(v["reach"])), "clicks": str(int(v["clicks"])),
                "inline_link_clicks": str(int(v["inline_link_clicks"])),
                "ctr": f"{(v['clicks'] / v['impressions'] * 100) if v['impressions'] else 0:.4f}",
                "actions": [{"action_type": "lead", "value": str(int(v["leads"]))}],
                "date_start": start.isoformat(), "date_stop": stop.isoformat(),
            }
            if v["purchases"]:
                row["actions"].append({"action_type": "omni_purchase",
                                       "value": str(int(v["purchases"]))})
                row["action_values"] = [{"action_type": "omni_purchase",
                                         "value": f"{v['revenue']:.2f}"}]
            if cmp:
                row["campaign_id"], row["campaign_name"] = cmp
            rows.append(row)
        return rows[:limit]
