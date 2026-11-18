"""Very small wrapper around the Meta Graph / Marketing API (graph.facebook.com).

No third-party platforms. Just HTTPS requests with your own token.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

GRAPH_URL = "https://graph.facebook.com"


class MetaAPIError(Exception):
    def __init__(self, message: str, code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class MetaAPI:
    def __init__(self, access_token: str, api_version: str = "v23.0", timeout: int = 60):
        if not access_token:
            raise MetaAPIError(
                "META_ACCESS_TOKEN is not set. Put your System User token in the "
                ".env file (local) or in the hosting dashboard (Render/Railway)."
            )
        self.token = access_token
        self.version = api_version
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- low level ----------
    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{GRAPH_URL}/{self.version}/{path.lstrip('/')}"

    @staticmethod
    def _encode(params: dict | None) -> dict:
        out = {}
        for k, v in (params or {}).items():
            if v is None:
                continue
            out[k] = json.dumps(v) if isinstance(v, (dict, list, bool)) else v
        return out

    def request(self, method: str, path: str, params: dict | None = None,
                data: dict | None = None, token: str | None = None) -> dict:
        params = self._encode(params)
        data = self._encode(data)
        auth = {"access_token": token or self.token}
        for attempt in range(3):
            try:
                if method == "GET":
                    resp = self.session.get(self._url(path), params={**params, **auth},
                                            timeout=self.timeout)
                else:
                    resp = self.session.request(method, self._url(path), params=params,
                                                data={**data, **auth}, timeout=self.timeout)
            except requests.RequestException as e:
                # Do not show the URL: it contains the access token.
                raise MetaAPIError(f"Network error talking to Meta: {type(e).__name__}") from None
            try:
                body = resp.json()
            except ValueError:
                body = {"error": {"message": resp.text[:500]}}
            if resp.ok and "error" not in body:
                return body
            err = body.get("error", {})
            code = err.get("code")
            # 4/17/32/613 = rate limits, 2 = temporary. Wait and retry.
            if code in (2, 4, 17, 32, 613) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            msg = err.get("error_user_msg") or err.get("message") or "Unknown Meta API error"
            raise MetaAPIError(f"Meta API error ({code}): {msg}", code=code, details=err)
        raise MetaAPIError("Meta API: too many retries")  # pragma: no cover

    def get(self, path: str, params: dict | None = None, token: str | None = None) -> dict:
        return self.request("GET", path, params=params, token=token)

    def post(self, path: str, data: dict | None = None) -> dict:
        return self.request("POST", path, data=data)

    def get_all(self, path: str, params: dict | None = None, limit: int = 200) -> list[dict]:
        """GET a list endpoint and follow paging until `limit` rows."""
        params = dict(params or {})
        params.setdefault("limit", min(limit, 100))
        rows: list[dict] = []
        body = self.get(path, params)
        while True:
            rows.extend(body.get("data", []))
            nxt = body.get("paging", {}).get("next")
            if not nxt or len(rows) >= limit:
                break
            try:
                body = self.session.get(nxt, timeout=self.timeout).json()
            except (requests.RequestException, ValueError) as e:
                raise MetaAPIError(f"Network error while paging: {type(e).__name__}") from None
            if "error" in body:
                raise MetaAPIError(body["error"].get("message", "paging error"))
        return rows[:limit]

    # ---------- helpers ----------
    def my_ad_accounts(self) -> list[dict]:
        return self.get_all(
            "me/adaccounts",
            {"fields": "id,account_id,name,currency,account_status,amount_spent,business{id,name}"},
            limit=500,
        )

    def account_info(self, account_id: str) -> dict:
        return self.get(account_id, {"fields": "id,name,currency,timezone_name,account_status"})

    def object_account(self, object_id: str) -> str:
        """Return the act_... id that a campaign / ad set / ad belongs to."""
        body = self.get(object_id, {"fields": "account_id"})
        return f"act_{body['account_id']}"

    def page_token(self, page_id: str) -> str:
        body = self.get(page_id, {"fields": "access_token"})
        token = body.get("access_token")
        if not token:
            raise MetaAPIError(
                "Could not get a Page token. Make sure the System User is assigned "
                "to this Page in Business Settings."
            )
        return token

    def upload_image_from_url(self, account_id: str, image_url: str) -> str:
        import base64

        try:
            r = requests.get(image_url, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise MetaAPIError(f"Could not download image_url: {e}") from None
        body = self.post(f"{account_id}/adimages",
                         {"bytes": base64.b64encode(r.content).decode()})
        images = body.get("images", {})
        first = next(iter(images.values()), None)
        if not first:
            raise MetaAPIError(f"Image upload failed: {body}")
        return first["hash"]
