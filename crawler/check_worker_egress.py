"""Inspect Cloudflare Worker outbound IPs, including the IP Tiki reports seeing."""

import argparse
import json
from collections import defaultdict

import requests

from config import HEADERS, REQUEST_TIMEOUT

IP_ECHO_URL = "https://api.ipify.org?format=json"
TIKI_PRODUCT_URL = "https://api.tiki.vn/product-detail/api/v1/products/{product_id}"


def worker_get(
    session: requests.Session, worker_url: str, target_url: str, timeout: int
) -> requests.Response:
    """Ask the Worker to fetch target_url; params safely encodes the nested URL."""
    return session.get(
        f"https://{worker_url}/",
        params={"url": target_url},
        headers=HEADERS,
        timeout=timeout,
    )


def check_worker(
    worker_url: str, product_id: int, samples: int, timeout: int
) -> list[dict]:
    results = []
    tiki_url = TIKI_PRODUCT_URL.format(product_id=product_id)
    with requests.Session() as session:
        for sample in range(1, samples + 1):
            result = {"worker": worker_url, "sample": sample}
            try:
                echo_response = worker_get(session, worker_url, IP_ECHO_URL, timeout)
                result["echo_status"] = echo_response.status_code
                result["echo_ip"] = echo_response.json().get("ip")
            except (requests.RequestException, ValueError) as error:
                result["echo_error"] = f"{type(error).__name__}: {error}"

            try:
                tiki_response = worker_get(session, worker_url, tiki_url, timeout)
                content_type = tiki_response.headers.get("Content-Type", "")
                result["tiki_status"] = tiki_response.status_code
                result["tiki_content_type"] = content_type
                # Tiki supplied this header in the previous curl response. If present,
                # it is the best available indication of the address Tiki observed.
                result["tiki_observed_ip"] = tiki_response.headers.get("x-request-ip")
                result["tiki_waf_suspected"] = (
                    tiki_response.status_code in (403, 429)
                    or "html" in content_type.lower()
                    or tiki_response.text.lstrip().startswith("<")
                )
            except requests.RequestException as error:
                result["tiki_error"] = f"{type(error).__name__}: {error}"
            results.append(result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Cloudflare Worker egress IPs and the IP reported by Tiki."
    )
    parser.add_argument("--start-worker", type=int, default=1)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--worker-domain", default="thienquang050906.workers.dev")
    parser.add_argument("--product-id", type=int, default=1391347)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT)
    args = parser.parse_args()

    all_results = []
    for number in range(args.start_worker, args.start_worker + args.workers):
        worker_url = f"tiki-crawler-{number:02d}.{args.worker_domain}"
        all_results.extend(
            check_worker(worker_url, args.product_id, args.samples, args.timeout)
        )

    for result in all_results:
        print(json.dumps(result, ensure_ascii=False))

    by_tiki_ip: dict[str, list[str]] = defaultdict(list)
    for result in all_results:
        if tiki_ip := result.get("tiki_observed_ip"):
            by_tiki_ip[tiki_ip].append(result["worker"])
    print("\nTiki-observed IP groups:")
    for ip_address, workers in by_tiki_ip.items():
        print(f"{ip_address}: {', '.join(workers)}")


if __name__ == "__main__":
    main()
