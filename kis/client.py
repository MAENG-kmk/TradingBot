# kis/client.py
import requests
from datetime import datetime, timedelta


class KISClient:
    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str):
        self._app_key    = app_key
        self._app_secret = app_secret
        self._token      = None
        self._token_exp  = None

    # ── 토큰 관리 ────────────────────────────────────────────────

    def _issue_token(self):
        url  = f"{self.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey":     self._app_key,
            "appsecret":  self._app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token     = data["access_token"]
        expires_in      = int(data.get("expires_in", 86400))
        self._token_exp = datetime.now() + timedelta(seconds=expires_in)

    def _ensure_token(self):
        if (self._token is None or
                self._token_exp is None or
                datetime.now() >= self._token_exp - timedelta(minutes=5)):
            self._issue_token()

    # ── REST 래퍼 ────────────────────────────────────────────────

    def _headers(self, tr_id: str) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "appkey":        self._app_key,
            "appsecret":     self._app_secret,
            "tr_id":         tr_id,
            "Content-Type":  "application/json",
        }

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        self._ensure_token()
        url  = f"{self.BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers(tr_id),
                            params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, tr_id: str, body: dict) -> dict:
        self._ensure_token()
        url  = f"{self.BASE_URL}{path}"
        resp = requests.post(url, headers=self._headers(tr_id),
                             json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
