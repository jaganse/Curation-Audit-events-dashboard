from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from etl.client import CurationAPIClient

BASE_URL = "https://myinstance.jfrog.io"
TOKEN = "fake-token"
START = datetime(2026, 3, 1, tzinfo=timezone.utc)
END = datetime(2026, 3, 10, tzinfo=timezone.utc)


def _mock_resp(data, total):
    m = MagicMock()
    m.json.return_value = {
        "data": data,
        "meta": {"total_count": total, "result_count": len(data)},
    }
    m.raise_for_status.return_value = None
    return m


def test_fetch_single_page():
    client = CurationAPIClient(BASE_URL, TOKEN)
    event = {"id": 1, "action": "approved", "package_name": "lodash"}
    with patch.object(client.session, "get", return_value=_mock_resp([event], 1)) as mock_get:
        results = list(client.fetch_events(dry_run=False, start=START, end=END))
    assert results == [event]
    assert mock_get.call_count == 1


def test_fetch_paginates():
    client = CurationAPIClient(BASE_URL, TOKEN)
    page1 = [{"id": i} for i in range(2000)]
    page2 = [{"id": i} for i in range(2000, 2500)]
    with patch.object(
        client.session,
        "get",
        side_effect=[_mock_resp(page1, 2500), _mock_resp(page2, 2500)],
    ) as mock_get:
        results = list(client.fetch_events(dry_run=False, start=START, end=END))
    assert len(results) == 2500
    assert mock_get.call_count == 2


def test_fetch_empty():
    client = CurationAPIClient(BASE_URL, TOKEN)
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)):
        results = list(client.fetch_events(dry_run=False, start=START, end=END))
    assert results == []


def test_dry_run_param_true():
    client = CurationAPIClient(BASE_URL, TOKEN)
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=True, start=START, end=END))
    assert mock_get.call_args.kwargs["params"]["dry_run"] == "true"


def test_dry_run_param_false():
    client = CurationAPIClient(BASE_URL, TOKEN)
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=False, start=START, end=END))
    assert mock_get.call_args.kwargs["params"]["dry_run"] == "false"


def test_include_total_param():
    client = CurationAPIClient(BASE_URL, TOKEN)
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=False, start=START, end=END))
    assert mock_get.call_args.kwargs["params"]["include_total"] == "true"


def test_auth_header():
    client = CurationAPIClient(BASE_URL, TOKEN)
    assert client.session.headers["Authorization"] == f"Bearer {TOKEN}"


def test_uses_correct_endpoint():
    client = CurationAPIClient(BASE_URL, TOKEN)
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=False, start=START, end=END))
    url = mock_get.call_args.args[0]
    assert url == f"{BASE_URL}/xray/api/v1/curation/audit/packages"
