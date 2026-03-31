from unittest.mock import MagicMock, patch, call

import pytest

from etl.main import run


def _env(monkeypatch):
    monkeypatch.setenv("JFROG_URL", "https://test.jfrog.io")
    monkeypatch.setenv("JFROG_TOKEN", "tok")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("LOOKBACK_DAYS", "2")


def test_fetches_both_modes(monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.fetch_events.return_value = iter([])
    with (
        patch("etl.main.CurationAPIClient", return_value=mock_client),
        patch("etl.main.psycopg2.connect", return_value=MagicMock()),
        patch("etl.main.upsert_events", return_value=0),
    ):
        run()
    dry_run_values = sorted(c.kwargs["dry_run"] for c in mock_client.fetch_events.call_args_list)
    assert dry_run_values == [False, True]


def test_upserts_policies_only_for_events_that_have_them(monkeypatch):
    _env(monkeypatch)
    event_with = {"id": 1, "policies": [{"policy_name": "p1"}]}
    event_without = {"id": 2, "policies": None}
    mock_client = MagicMock()
    mock_client.fetch_events.side_effect = [iter([event_with, event_without]), iter([])]
    mock_upsert_policies = MagicMock(return_value=1)
    with (
        patch("etl.main.CurationAPIClient", return_value=mock_client),
        patch("etl.main.psycopg2.connect", return_value=MagicMock()),
        patch("etl.main.upsert_events", return_value=2),
        patch("etl.main.upsert_policies", mock_upsert_policies),
    ):
        run()
    assert mock_upsert_policies.call_count == 1
    assert mock_upsert_policies.call_args.args[1] == 1  # event_id=1


def test_commits_after_each_batch(monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.fetch_events.return_value = iter([])
    mock_conn = MagicMock()
    with (
        patch("etl.main.CurationAPIClient", return_value=mock_client),
        patch("etl.main.psycopg2.connect", return_value=mock_conn),
        patch("etl.main.upsert_events", return_value=0),
    ):
        run()
    # Two modes (dry_run=False, dry_run=True) → 2 commits + 1 MV refresh commit = 3 total
    assert mock_conn.commit.call_count == 3


def test_closes_connection_on_error(monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.fetch_events.side_effect = RuntimeError("API down")
    mock_conn = MagicMock()
    with (
        patch("etl.main.CurationAPIClient", return_value=mock_client),
        patch("etl.main.psycopg2.connect", return_value=mock_conn),
        patch("etl.main.upsert_events", return_value=0),
    ):
        with pytest.raises(RuntimeError):
            run()
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()


def test_lookback_days_default(monkeypatch):
    monkeypatch.setenv("JFROG_URL", "https://test.jfrog.io")
    monkeypatch.setenv("JFROG_TOKEN", "tok")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    # LOOKBACK_DAYS not set — should default to 2
    monkeypatch.delenv("LOOKBACK_DAYS", raising=False)
    mock_client = MagicMock()
    mock_client.fetch_events.return_value = iter([])
    with (
        patch("etl.main.CurationAPIClient", return_value=mock_client),
        patch("etl.main.psycopg2.connect", return_value=MagicMock()),
        patch("etl.main.upsert_events", return_value=0),
    ):
        run()  # should not raise
    assert mock_client.fetch_events.call_count == 2
