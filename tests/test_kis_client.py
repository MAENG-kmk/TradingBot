# tests/test_kis_client.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.abspath("."))
from kis.client import KISClient


FAKE_KEY    = "test_key"
FAKE_SECRET = "test_secret"
FAKE_TOKEN  = "test_access_token"


def make_client_with_token():
    """이미 토큰이 발급된 상태의 클라이언트 반환"""
    client = KISClient(FAKE_KEY, FAKE_SECRET)
    client._token     = FAKE_TOKEN
    client._token_exp = datetime.now() + timedelta(hours=23)
    return client


def test_token_injected_in_headers():
    """get() 호출 시 Authorization 헤더가 자동 주입되어야 한다"""
    client = make_client_with_token()
    with patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"output": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client.get("/some/path", "TR_ID_TEST", {"param": "value"})

        call_kwargs = mock_get.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
        assert headers["appkey"]        == FAKE_KEY
        assert headers["appsecret"]     == FAKE_SECRET
        assert headers["tr_id"]         == "TR_ID_TEST"


def test_token_refresh_when_expired():
    """토큰이 만료되었을 때 _issue_token()이 호출되어야 한다"""
    client = KISClient(FAKE_KEY, FAKE_SECRET)
    client._token     = "old_token"
    client._token_exp = datetime.now() - timedelta(minutes=1)  # 만료

    with patch.object(client, "_issue_token") as mock_issue, \
         patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        mock_issue.side_effect = lambda: setattr(client, '_token', 'new_token') or \
                                         setattr(client, '_token_exp',
                                                 datetime.now() + timedelta(hours=24))

        client.get("/path", "TR", {})
        mock_issue.assert_called_once()


def test_token_not_refreshed_when_valid():
    """토큰이 유효하면 _issue_token()이 호출되지 않아야 한다"""
    client = make_client_with_token()
    with patch.object(client, "_issue_token") as mock_issue, \
         patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client.get("/path", "TR", {})
        mock_issue.assert_not_called()
