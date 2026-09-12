import html
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import requests
import ujson as json

from config import HTML_TAG_REGEX


def load_and_batch_ids(file_path: Path, batch_size: int = 1000) -> tuple[list[list[int]], int]:
    """Read, validate, de-duplicate, and batch product IDs."""
    if not file_path.exists():
        return [], 0
    with open(file_path, "r", encoding="utf-8") as source:
        valid_ids = [int(line.strip()) for line in source if line.strip().isdigit()]
    unique_ids = list(dict.fromkeys(valid_ids))
    return [unique_ids[i : i + batch_size] for i in range(0, len(unique_ids), batch_size)], len(unique_ids)


def clean_description(text: Optional[str]) -> Optional[str]:
    """Normalize description whitespace without removing paragraph boundaries."""
    if not text:
        return text
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clean_html(raw_html: Optional[str]) -> str:
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    return clean_description(html.unescape(HTML_TAG_REGEX.sub(" ", text))) or ""


def extract_product_info(raw_data: dict) -> dict:
    images = []
    if isinstance(raw_data.get("images"), list):
        for image in raw_data["images"]:
            if isinstance(image, dict):
                image_url = image.get("base_url") or image.get("large_url") or image.get("url")
                if image_url:
                    images.append(image_url)
    return {"id": raw_data.get("id"), "name": raw_data.get("name"), "url_key": raw_data.get("url_key"), "price": raw_data.get("price"), "description": clean_html(raw_data.get("description")), "images": images}


def _atomic_write_json(path: Path, data: object) -> None:
    """Write JSON durably, then atomically replace the destination."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with open(temporary_path, "w", encoding="utf-8") as destination:
        json.dump(data, destination, ensure_ascii=False, indent=2)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary_path, path)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a checkpoint and repair an incomplete final JSONL record."""
    if not path.exists():
        return []

    with open(path, "rb") as source:
        lines = []
        while raw_line := source.readline():
            lines.append((source.tell() - len(raw_line), raw_line))

    records = []
    non_empty_indexes = [index for index, (_, line) in enumerate(lines) if line.strip()]
    last_non_empty_index = non_empty_indexes[-1] if non_empty_indexes else -1
    for index, (offset, raw_line) in enumerate(lines):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            if index == last_non_empty_index:
                # The only durable repair we make is removing a partial final record.
                with open(path, "r+b") as checkpoint:
                    checkpoint.truncate(offset)
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


class BatchCheckpoint:
    """Append-only recovery logs and atomic final output for one batch."""

    def __init__(self, run_dir: Path, batch_num: int, sync_interval: int = 50):
        self.run_dir = run_dir
        self.batch_num = batch_num
        self.sync_interval = sync_interval
        self.success_dir = run_dir / "success"
        self.not_found_dir = run_dir / "not_found"
        self.final_dir = run_dir / "final"
        for directory in (self.success_dir, self.not_found_dir, self.final_dir):
            directory.mkdir(parents=True, exist_ok=True)
        file_name = f"{batch_num:04d}"
        self.success_path = self.success_dir / f"success_batch_{file_name}.jsonl"
        self.not_found_path = self.not_found_dir / f"not_found_batch_{file_name}.jsonl"
        self.final_path = self.final_dir / f"tiki_batch_{file_name}.json"
        self._success_file = None
        self._not_found_file = None
        self._records_since_sync = 0

    @property
    def finalized(self) -> bool:
        return self.final_path.exists()

    def load_completed(self) -> tuple[list[dict], set[int]]:
        success_records = _read_jsonl(self.success_path)
        not_found_records = _read_jsonl(self.not_found_path)
        completed_ids = {int(record["id"]) for record in [*success_records, *not_found_records] if str(record.get("id", "")).isdigit()}
        return success_records, completed_ids

    def open(self) -> None:
        self._success_file = open(self.success_path, "a", encoding="utf-8")
        self._not_found_file = open(self.not_found_path, "a", encoding="utf-8")

    def _append(self, handle, record: dict) -> bool:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._records_since_sync += 1
        if self._records_since_sync >= self.sync_interval:
            self.flush()
            return True
        return False

    def record_success(self, product: dict) -> bool:
        if self._success_file is None:
            raise RuntimeError("Checkpoint is not open")
        return self._append(self._success_file, product)

    def record_not_found(self, product_id: int, status: int) -> bool:
        if self._not_found_file is None:
            raise RuntimeError("Checkpoint is not open")
        return self._append(self._not_found_file, {"id": product_id, "status": status, "timestamp": datetime.now(UTC).isoformat()})

    def flush(self) -> None:
        for handle in (self._success_file, self._not_found_file):
            if handle is not None:
                handle.flush()
                os.fsync(handle.fileno())
        self._records_since_sync = 0

    def write_state(self, worker_id: str, success_count: int, not_found_count: int) -> None:
        _atomic_write_json(self.run_dir / "state.json", {"worker_id": worker_id, "current_batch": self.batch_num, "success_count": success_count, "not_found_count": not_found_count, "updated_at": datetime.now(UTC).isoformat()})

    def finalize(self) -> Path:
        self.flush()
        records, _ = self.load_completed()
        unique_records = list({record.get("id"): record for record in records}.values())
        _atomic_write_json(self.final_path, unique_records)
        return self.final_path

    def close(self) -> None:
        self.flush()
        for attribute in ("_success_file", "_not_found_file"):
            handle = getattr(self, attribute)
            if handle is not None:
                handle.close()
                setattr(self, attribute, None)


def fetch_product_data(session: requests.Session, cloudflare_worker_url: str, product_id: int, batch_num: int, event_logger: logging.Logger, not_found_logger: logging.Logger, waf_retry_delay: float, max_waf_retries: int, headers: dict, request_timeout: int, delay: float) -> tuple[Optional[dict], Optional[int]]:
    """Fetch one product; return (product, terminal_not_found_status)."""
    target_url = f"https://api.tiki.vn/product-detail/api/v1/products/{product_id}"
    worker_url = f"https://{cloudflare_worker_url}/"
    msg_start = f"Batch {batch_num:04d} | Fetching ID {product_id}..."
    print(msg_start, end=" ")
    event_logger.info(msg_start)
    waf_retries = 0
    current_waf_delay = waf_retry_delay
    while True:
        try:
            response = session.get(worker_url, params={"url": target_url}, headers=headers, timeout=request_timeout)
            event_logger.info(
                "ID %s -> request URL %s", product_id, response.request.url
            )
            if response.status_code == 200:
                try:
                    product = extract_product_info(response.json())
                    print(f"-> OK ({product.get('name', '')[:25]}...)")
                    event_logger.info("ID %s -> OK", product_id)
                    return product, None
                except ValueError:
                    waf_retries += 1
                    cooldown = 3600 if waf_retries > max_waf_retries else max(delay, current_waf_delay)
                    message = (
                        "ID %s -> WAF/invalid JSON (HTTP 200) via %s; "
                        "retry %s/%s, cooldown %ss"
                    )
                    event_logger.warning(
                        message,
                        product_id,
                        cloudflare_worker_url,
                        waf_retries,
                        max_waf_retries,
                        cooldown,
                    )
                    print(message % (product_id, cloudflare_worker_url, waf_retries, max_waf_retries, cooldown))
            elif response.status_code in (404, 410):
                print(f"-> {response.status_code} Not Found")
                event_logger.info("ID %s -> %s Not Found", product_id, response.status_code)
                not_found_logger.info("%s", product_id)
                return None, response.status_code
            elif response.status_code in (403, 429):
                waf_retries += 1
                cooldown = 3600 if waf_retries > max_waf_retries else max(delay, current_waf_delay)
                message = "ID %s -> WAF HTTP %s via %s; retry %s/%s, cooldown %ss"
                event_logger.warning(
                    message,
                    product_id,
                    response.status_code,
                    cloudflare_worker_url,
                    waf_retries,
                    max_waf_retries,
                    cooldown,
                )
                print(message % (product_id, response.status_code, cloudflare_worker_url, waf_retries, max_waf_retries, cooldown))
            else:
                waf_retries += 1
                event_logger.warning("ID %s -> HTTP %s", product_id, response.status_code)
                print(f"-> HTTP {response.status_code}")
        except requests.RequestException as error:
            waf_retries += 1
            event_logger.warning("ID %s -> %s", product_id, type(error).__name__)
            print(f"-> NETWORK ERROR ({type(error).__name__})")
        if waf_retries > max_waf_retries:
            event_logger.critical("ID %s exceeded retries; cooling down for 3600s", product_id)
            time.sleep(3600)
            waf_retries = 0
            current_waf_delay = waf_retry_delay
        else:
            time.sleep(max(delay, current_waf_delay))
            current_waf_delay *= 2
