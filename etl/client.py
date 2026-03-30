from collections.abc import Iterator
from datetime import datetime

import requests


class CurationAPIClient:
    PAGE_SIZE = 2000
    ENDPOINT = "/xray/api/v1/curation/audit/packages"

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def fetch_events(self, dry_run: bool, start: datetime, end: datetime) -> "Iterator[dict]":
        """Yield all audit events for the time window, paginating automatically."""
        if start >= end:
            raise ValueError(f"start must be before end (got start={start!r}, end={end!r})")

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
                raise ValueError(f"Unexpected API response — missing 'meta.total_count'. Body keys: {list(body.keys())}")
            total = meta["total_count"]

            events = body.get("data", [])
            yield from events
            offset += len(events)

            if not events:
                break
