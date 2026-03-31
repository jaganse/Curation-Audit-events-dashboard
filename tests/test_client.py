from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from etl.client import CurationAPIClient

BASE_URL = "https://myinstance.jfrog.io"
TOKEN = "fake-token"
START = datetime(2026, 3, 1, tzinfo=timezone.utc)
END = datetime(2026, 3, 5, tzinfo=timezone.utc)  # 4 days — fits in one 7-day chunk


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
    assert mock_get.call_args_list[0].kwargs["params"]["offset"] == 0
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == 2000


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


def test_large_window_is_chunked():
    """A 30-day window is split into 7-day chunks (4 full + 1 partial = 5 requests)."""
    client = CurationAPIClient(BASE_URL, TOKEN)
    big_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    big_end = datetime(2026, 1, 31, tzinfo=timezone.utc)  # 30 days → 5 chunks
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=False, start=big_start, end=big_end))
    assert mock_get.call_count == 5


def test_chunk_boundaries_are_contiguous():
    """Each chunk's end becomes the next chunk's start — no gaps or overlaps."""
    client = CurationAPIClient(BASE_URL, TOKEN)
    big_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    big_end = datetime(2026, 1, 22, tzinfo=timezone.utc)  # 21 days → exactly 3 chunks
    with patch.object(client.session, "get", return_value=_mock_resp([], 0)) as mock_get:
        list(client.fetch_events(dry_run=False, start=big_start, end=big_end))
    assert mock_get.call_count == 3
    starts = [c.kwargs["params"]["created_at_start"] for c in mock_get.call_args_list]
    ends = [c.kwargs["params"]["created_at_end"] for c in mock_get.call_args_list]
    assert starts == ["2026-01-01T00:00:00Z", "2026-01-08T00:00:00Z", "2026-01-15T00:00:00Z"]
    assert ends == ["2026-01-08T00:00:00Z", "2026-01-15T00:00:00Z", "2026-01-22T00:00:00Z"]
