from datetime import datetime

import requests


class CurationAPIClient:
    PAGE_SIZE = 2000
    ENDPOINT = "/xray/api/v1/curation/audit/packages"

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def fetch_events(self, dry_run: bool, start: datetime, end: datetime):
        """Yield all audit events for the time window, paginating automatically."""
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

            if total is None:
                total = body["meta"]["total_count"]

            events = body.get("data", [])
            yield from events
            offset += len(events)

            if not events:
                break
