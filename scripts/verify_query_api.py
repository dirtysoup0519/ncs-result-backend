"""Smoke-test the query API contract used by the Vue dashboard."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINTS = (
    "/api/v1/meta/capabilities",
    "/api/v1/meta/filter-options?topic=overview",
    "/api/v1/dashboard/manifest",
    "/api/v1/meta/data-status",
    "/api/v1/dashboard/overview",
    "/api/v1/audience/platform-distribution",
    "/api/v1/charging/duration-distribution",
    "/api/v1/charging/weekday-weekend",
    "/api/v1/stations/ranking",
    "/api/v1/revenue/trend",
    "/api/v1/charging/process-summary",
    "/api/v1/charging/station-hour-heatmap?metric=kwh",
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify all dashboard query endpoints")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--api-key")
    args = parser.parse_args(argv)
    failures = []
    for endpoint in ENDPOINTS:
        request = Request(args.base_url.rstrip("/") + endpoint, headers={"X-API-Key": args.api_key} if args.api_key else {})
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status != 200 or payload.get("code") != "OK":
                    failures.append({"endpoint": endpoint, "status": response.status, "code": payload.get("code")})
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            failures.append({"endpoint": endpoint, "error": str(exc)})
    print(json.dumps({"checked": len(ENDPOINTS), "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
