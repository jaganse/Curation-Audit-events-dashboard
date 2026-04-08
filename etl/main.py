import json
import os
import pathlib
import urllib.parse
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

from etl.client import CurationAPIClient
from etl.storage import upsert_events, upsert_policies


def _load_instances() -> list[dict]:
    """Load JFrog instance configs from instances.json, or fall back to env vars.

    instances.json format:
        [{"name": "prod", "url": "https://mycompany.jfrog.io", "token": "eyJ..."}]

    Fallback (single instance): reads JFROG_URL + JFROG_TOKEN from environment,
    deriving the instance name from the URL hostname.
    """
    p = pathlib.Path("instances.json")
    if p.exists():
        with p.open() as f:
            return json.load(f)
    url = os.environ["JFROG_URL"]
    name = urllib.parse.urlparse(url).hostname or url
    return [{"name": name, "url": url, "token": os.environ["JFROG_TOKEN"]}]


def run():
    load_dotenv()

    instances = _load_instances()
    database_url = os.environ["DATABASE_URL"]
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", "2"))

    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=lookback_days)

    conn = psycopg2.connect(database_url)

    try:
        total_events = 0
        total_policies = 0

        for inst in instances:
            jfrog_instance = inst["name"]
            client = CurationAPIClient(inst["url"], inst["token"])
            print(f"Processing instance: {jfrog_instance} ({inst['url']})")

            for is_dry_run in (False, True):
                mode = "dry-run" if is_dry_run else "real"
                print(f"  Fetching {mode} events from {start.date()} to {now.date()}...")
                events = list(client.fetch_events(dry_run=is_dry_run, start=start, end=now))
                count = upsert_events(conn, events, is_dry_run=is_dry_run, jfrog_instance=jfrog_instance)
                total_events += count

                for event in events:
                    if event.get("policies"):
                        total_policies += upsert_policies(
                            conn, event["id"], event["policies"], jfrog_instance
                        )

                # Commit each mode independently — real and dry-run are separate streams.
                # A re-run will idempotently upsert already-committed events.
                conn.commit()
                print(f"  {mode}: {count} events upserted")

        print(f"Done. {total_events} events, {total_policies} policies processed.")
        print("Refreshing materialized view mv_download_windows...")
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_download_windows")
        conn.commit()
        print("Materialized view refreshed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
