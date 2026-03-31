"""Integration tests for the mv_download_windows materialized view.

Requires a running PostgreSQL instance with the schema applied (including the
materialized view from init.sql). Set DATABASE_URL to point at it.

These tests insert events with controlled timestamps, refresh the MV, then
assert on is_window_start and cumulative_window_number.

Algorithm note: the MV uses gap-from-previous (not gap-from-window-start).
For the edge case T+0, T+6h, T+13h within the same group:
  - Gap T+0→T+6h is 6h < 12h → no new window
  - Gap T+6h→T+13h is 7h < 12h → no new window (approximation: returns 1 window)
The greedy algorithm (as in GetAuditTimeWindow.py) would return 2 windows.
This edge case is documented and accepted.
"""

import os
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

DB_URL = os.environ.get("DATABASE_URL", "postgresql://audit:audit@localhost:5432/audit")

TEST_ID_BASE = 9_998_000

_BASE_TIME = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    try:
        c = psycopg2.connect(DB_URL)
    except Exception:
        pytest.skip("PostgreSQL not available")
    with c.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_download_windows'"
        )
        if cur.fetchone() is None:
            c.close()
            pytest.skip("mv_download_windows not found — run migrations first")
    yield c
    c.rollback()
    with c.cursor() as cur:
        cur.execute("DELETE FROM audit_events WHERE package_name LIKE 'win-test-%'")
    c.commit()
    c.close()


def _insert_event(conn, seq, package_name, created_at, action="blocked", is_dry_run=False):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audit_events
               (id, created_at, action, is_dry_run, package_type, package_name,
                package_version, username)
               VALUES (%s, %s, %s, %s, 'npm', %s, '1.0.0', 'win-user@test.com')
               ON CONFLICT (id) DO NOTHING""",
            (TEST_ID_BASE + seq, created_at, action, is_dry_run, package_name),
        )


def _refresh(conn):
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW mv_download_windows")
    conn.commit()


def _windows(conn, package_name):
    """Return (is_window_start, cumulative_window_number) rows ordered by created_at."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT is_window_start, cumulative_window_number
               FROM mv_download_windows
               WHERE package_name = %s AND username = 'win-user@test.com'
               ORDER BY created_at""",
            (package_name,),
        )
        return cur.fetchall()


def test_single_event_is_one_window(conn):
    _insert_event(conn, 1, "win-test-single", _BASE_TIME)
    conn.commit()
    _refresh(conn)
    rows = _windows(conn, "win-test-single")
    assert len(rows) == 1
    assert rows[0] == (1, 1)  # first event always starts a window


def test_ci_burst_is_one_window(conn):
    """50 events within 10 minutes = 1 session."""
    for i in range(50):
        _insert_event(conn, 100 + i, "win-test-burst", _BASE_TIME + timedelta(minutes=i))
    conn.commit()
    _refresh(conn)
    rows = _windows(conn, "win-test-burst")
    assert len(rows) == 50
    assert rows[0][0] == 1   # first is window start
    assert all(r[0] == 0 for r in rows[1:])   # rest are NOT window starts
    assert all(r[1] == 1 for r in rows)        # all in window #1


def test_multi_day_attempts_are_separate_windows(conn):
    """Events on Mon, Wed, Fri → 3 distinct sessions (all gaps > 12h)."""
    days = [0, 2, 4]
    for i, day in enumerate(days):
        _insert_event(conn, 200 + i, "win-test-multiday", _BASE_TIME + timedelta(days=day))
    conn.commit()
    _refresh(conn)
    rows = _windows(conn, "win-test-multiday")
    assert len(rows) == 3
    assert all(r[0] == 1 for r in rows)           # each is a new window start
    assert [r[1] for r in rows] == [1, 2, 3]       # window numbers 1, 2, 3


def test_exact_12h_boundary_starts_new_window(conn):
    """Gap of exactly 12h should start a new window."""
    _insert_event(conn, 300, "win-test-boundary", _BASE_TIME)
    _insert_event(conn, 301, "win-test-boundary", _BASE_TIME + timedelta(hours=12))
    conn.commit()
    _refresh(conn)
    rows = _windows(conn, "win-test-boundary")
    assert len(rows) == 2
    assert rows[0] == (1, 1)
    assert rows[1] == (1, 2)


def test_gap_just_under_12h_is_same_window(conn):
    """Gap of 11h 59m should NOT start a new window."""
    _insert_event(conn, 400, "win-test-under12", _BASE_TIME)
    _insert_event(conn, 401, "win-test-under12", _BASE_TIME + timedelta(hours=11, minutes=59))
    conn.commit()
    _refresh(conn)
    rows = _windows(conn, "win-test-under12")
    assert len(rows) == 2
    assert rows[0] == (1, 1)
    assert rows[1] == (0, 1)  # same window


def test_approved_and_blocked_counted_separately(conn):
    """Approved and blocked events for the same package are independent groups."""
    _insert_event(conn, 500, "win-test-split", _BASE_TIME, action="blocked")
    _insert_event(conn, 501, "win-test-split", _BASE_TIME + timedelta(hours=1), action="approved")
    _insert_event(conn, 502, "win-test-split", _BASE_TIME + timedelta(hours=25), action="blocked")
    conn.commit()
    _refresh(conn)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT action, SUM(is_window_start) AS sessions
               FROM mv_download_windows
               WHERE package_name = 'win-test-split' AND username = 'win-user@test.com'
               GROUP BY action ORDER BY action""",
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}
    assert rows["approved"] == 1   # 1 approved event = 1 session
    assert rows["blocked"] == 2    # 2 blocked events with 25h gap = 2 sessions
