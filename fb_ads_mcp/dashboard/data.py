"""Gets the numbers for the dashboard from Meta (or from demo data)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ..config import Client
from ..insights import INSIGHT_FIELDS, summarize_row, total_of
from ..meta_api import MetaAPIError
from .dates import Period


def add_ratios(t: dict) -> dict:
    """CTR and CPM for a total (total_of already gives CPC, CPL, ROAS)."""
    imp = t.get("impressions") or 0
    t["ctr_percent"] = round(t.get("clicks", 0) / imp * 100, 2) if imp else None
    t["cpm"] = round(t.get("spend", 0) * 1000 / imp, 2) if imp else None
    return t


class TTLCache:
    def __init__(self, seconds: int):
        self.seconds = seconds
        self._data: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
        if hit and time.time() - hit[0] < self.seconds:
            return hit[1]
        return None

    def set(self, key, value):
        with self._lock:
            if len(self._data) > 2000:
                self._data.clear()
            self._data[key] = (time.time(), value)


class DashboardData:
    def __init__(self, api, cache_seconds: int = 300, workers: int = 6):
        self.api = api
        self.cache = TTLCache(cache_seconds)
        self.workers = workers

    def _insights(self, acc: str, period: Period, refresh: bool, **extra) -> list[dict]:
        key = (acc, period.cache_key(), tuple(sorted(extra.items())))
        if not refresh:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        params = {"fields": ",".join(INSIGHT_FIELDS), "level": "account",
                  **period.meta_params(), **extra}
        rows = [summarize_row(r) for r in
                self.api.get_all(f"{acc}/insights", params, limit=500)]
        self.cache.set(key, rows)
        return rows

    def _currency(self, acc: str, rows: list[dict]) -> str | None:
        for r in rows:
            if r.get("account_currency"):
                return r["account_currency"]
        hit = self.cache.get(("currency", acc))
        if hit:
            return hit
        try:
            cur = self.api.account_info(acc).get("currency")
        except MetaAPIError:
            return None
        if cur:
            self.cache.set(("currency", acc), cur)
        return cur

    def client_summary(self, c: Client, period: Period, refresh: bool = False) -> dict:
        try:
            rows = self._insights(c.ad_account_id, period, refresh)
            total = add_ratios(total_of(rows))
            return {"client": c, "total": total,
                    "currency": self._currency(c.ad_account_id, rows), "error": None}
        except (MetaAPIError, ValueError) as e:
            return {"client": c, "total": None, "currency": None, "error": str(e)}

    def overview(self, clients: dict[str, Client], period: Period,
                 refresh: bool = False) -> dict:
        items = list(clients.values())
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            rows = list(pool.map(lambda c: self.client_summary(c, period, refresh), items))
        rows.sort(key=lambda r: (r["total"] or {}).get("spend", -1), reverse=True)
        by_cur: dict[str, list] = {}
        for r in rows:
            if r["total"]:
                by_cur.setdefault(r["currency"] or "?", []).append(r["total"])
        totals = {cur: add_ratios(total_of(ts)) for cur, ts in by_cur.items()}
        return {"rows": rows, "totals": totals}

    def client_detail(self, c: Client, period: Period, refresh: bool = False) -> dict:
        summary = self.client_summary(c, period, refresh)
        if summary["error"]:
            return {**summary, "daily": [], "campaigns": [], "step": 1}
        step = period.time_increment()
        try:
            daily = self._insights(c.ad_account_id, period, refresh, time_increment=step)
            campaigns = self._insights(c.ad_account_id, period, refresh, level="campaign")
        except (MetaAPIError, ValueError) as e:
            return {**summary, "daily": [], "campaigns": [], "step": step, "error": str(e)}
        daily.sort(key=lambda r: r.get("date_start", ""))
        campaigns = [add_ratios(dict(r)) for r in campaigns]
        campaigns.sort(key=lambda r: r.get("spend", 0), reverse=True)
        return {**summary, "daily": daily, "campaigns": campaigns, "step": step}
