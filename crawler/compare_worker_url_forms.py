"""Compare raw and percent-encoded nested URLs sent to one Cloudflare Worker."""

import argparse
import hashlib
import json
import time

import requests

from config import HEADERS, REQUEST_TIMEOUT


def summarize(name: str, response: requests.Response) -> dict:
    body = response.content
    summary = {
        "form": name,
        "request_url": str(response.request.url),
        "status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "tiki_observed_ip": response.headers.get("x-request-ip"),
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "looks_like_html": body.lstrip().startswith(b"<"),
    }
    try:
        payload = response.json()
        summary["json_product_id"] = payload.get("id") if isinstance(payload, dict) else None
    except ValueError:
        summary["json_product_id"] = None
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--worker-url", default="tiki-crawler-05.thienquang050906.workers.dev"
    )
    parser.add_argument("--product-id", type=int, default=1391347)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT)
    parser.add_argument("--pause", type=float, default=2.0)
    args = parser.parse_args()

    target_url = (
        f"https://api.tiki.vn/product-detail/api/v1/products/{args.product_id}"
    )
    worker_url = f"https://{args.worker_url}/"
    raw_url = f"{worker_url}?url={target_url}"

    with requests.Session() as session:
        raw_response = session.get(raw_url, headers=HEADERS, timeout=args.timeout)
        print(json.dumps(summarize("raw", raw_response), ensure_ascii=False, indent=2))
        time.sleep(args.pause)
        params_response = session.get(
            worker_url,
            params={"url": target_url},
            headers=HEADERS,
            timeout=args.timeout,
        )
        print(json.dumps(summarize("requests_params", params_response), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
