"""Settings and client list.

Secrets come ONLY from environment variables (or a local .env file that is
never committed). The client list comes from clients.json or from the
CLIENTS_JSON environment variable (handy on Render / Railway).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # .env is optional, mainly for running on your own computer
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass
class Client:
    key: str  # short name used in tools, e.g. "pizza_hub"
    name: str  # nice display name
    ad_account_id: str  # always stored as "act_123..."
    page_id: str | None = None
    max_daily_budget: float | None = None  # in account currency, e.g. 50.0
    max_lifetime_budget: float | None = None
    notes: str | None = None
    extra: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "client": self.key,
            "name": self.name,
            "ad_account_id": self.ad_account_id,
            "page_id": self.page_id,
            "max_daily_budget": self.max_daily_budget,
            "max_lifetime_budget": self.max_lifetime_budget,
            "notes": self.notes,
        }


def normalize_account_id(value: str) -> str:
    value = str(value).strip()
    return value if value.startswith("act_") else f"act_{value}"


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def parse_clients(data: dict) -> dict[str, Client]:
    """Accepts {"clients": {"key": {...}}} or a plain {"key": {...}}."""
    raw = data.get("clients", data)
    clients: dict[str, Client] = {}
    for key, c in raw.items():
        if not isinstance(c, dict):
            continue
        if "ad_account_id" not in c:
            raise ValueError(f"Client '{key}' has no ad_account_id")
        clients[key.lower()] = Client(
            key=key.lower(),
            name=c.get("name", key),
            ad_account_id=normalize_account_id(c["ad_account_id"]),
            page_id=str(c["page_id"]) if c.get("page_id") else None,
            max_daily_budget=_to_float(c.get("max_daily_budget")),
            max_lifetime_budget=_to_float(c.get("max_lifetime_budget")),
            notes=c.get("notes"),
        )
    return clients


def load_clients() -> dict[str, Client]:
    env_json = os.getenv("CLIENTS_JSON", "").strip()
    if env_json:
        return parse_clients(json.loads(env_json))
    path = Path(os.getenv("CLIENTS_FILE", "clients.json"))
    if not path.exists():
        return {}
    return parse_clients(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class Settings:
    access_token: str
    api_version: str
    global_max_daily_budget: float | None
    global_max_lifetime_budget: float | None
    allow_unknown_accounts: bool
    mcp_auth_token: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            access_token=os.getenv("META_ACCESS_TOKEN", "").strip(),
            api_version=os.getenv("META_API_VERSION", "v23.0").strip(),
            global_max_daily_budget=_to_float(os.getenv("GLOBAL_MAX_DAILY_BUDGET")),
            global_max_lifetime_budget=_to_float(os.getenv("GLOBAL_MAX_LIFETIME_BUDGET")),
            allow_unknown_accounts=os.getenv("ALLOW_UNKNOWN_ACCOUNTS", "false").lower()
            in ("1", "true", "yes"),
            mcp_auth_token=os.getenv("MCP_AUTH_TOKEN", "").strip() or None,
        )
