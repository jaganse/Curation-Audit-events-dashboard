from collections.abc import Iterator
from datetime import datetime, timedelta

import requests


class CurationAPIClient:
    PAGE_SIZE = 2000
    DATE_CHUNK_DAYS = 7
    ENDPOINT = "/xray/api/v1/curation/audit/packages"

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def fetch_events(self, dry_run: bool, start: datetime, end: datetime) -> "Iterator[dict]":
        """Yield all audit events for the time window.

        The JFrog API rejects date ranges longer than ~7 days with a 400 error.
        This method splits the window into DATE_CHUNK_DAYS-sized chunks and
        paginates each independently, so callers can request any lookback period.
        """
        if start >= end:
            raise ValueError(f"start must be before end (got start={start!r}, end={end!r})")

        chunk_start = start
        chunk_delta = timedelta(days=self.DATE_CHUNK_DAYS)

        while chunk_start < end:
            chunk_end = min(chunk_start + chunk_delta, end)
            yield from self._fetch_chunk(dry_run, chunk_start, chunk_end)
            chunk_start = chunk_end

    def _fetch_chunk(self, dry_run: bool, start: datetime, end: datetime) -> "Iterator[dict]":
        """Yield all events for a single date chunk, paginating automatically."""
        url = f"{self.base_url}{self.ENDPOINT}"
        offset = 0
        total = None

        while total is None or offset < total:
            params = {
                "dry_run": str(dry_run).lower(),
                "num_of_rows": self.PAGE_SIZE,
                "offset": offset,
                "include_total": "true",
                "created_at_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "created_at_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order_by": "id",
                "direction": "asc",
            }
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()

            meta = body.get("meta")
            if not meta or "total_count" not in meta:
                raise ValueError(
                    f"Unexpected API response — missing 'meta.total_count'. "
                    f"Body keys: {list(body.keys())}"
                )
            total = meta["total_count"]

            events = body.get("data") or []
            yield from events
            offset += len(events)

            if not events:
                break
