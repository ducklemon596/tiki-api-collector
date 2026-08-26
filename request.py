import html
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import requests
from tqdm import tqdm
import ujson as json

# ==========================================
# CẤU HÌNH LOGGING
# ==========================================

# 1. Logger tổng hợp sự kiện
event_logger = logging.getLogger("event_logger")
event_logger.setLevel(logging.INFO)
event_handler = logging.FileHandler("events_history.log", encoding="utf-8")
event_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)
event_logger.addHandler(event_handler)

# 2. Logger ghi nhận ID lỗi ra CSV
error_logger = logging.getLogger("error_logger")
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler("failed_products.csv", encoding="utf-8")
error_handler.setFormatter(logging.Formatter("%(asctime)s,%(message)s"))
error_logger.addHandler(error_handler)

if (
    not os.path.exists("failed_products.csv")
    or os.path.getsize("failed_products.csv") == 0
):
    with open("failed_products.csv", "w", encoding="utf-8") as f:
        f.write("timestamp,product_id,error_reason\n")

# 3. Logger ghi nhận ID thành công ra CSV
success_logger = logging.getLogger("success_logger")
success_logger.setLevel(logging.INFO)
success_handler = logging.FileHandler("successful_products.csv", encoding="utf-8")
success_handler.setFormatter(logging.Formatter("%(asctime)s,%(message)s"))
success_logger.addHandler(success_handler)

if (
    not os.path.exists("successful_products.csv")
    or os.path.getsize("successful_products.csv") == 0
):
    with open("successful_products.csv", "w", encoding="utf-8") as f:
        f.write("timestamp,product_id,status\n")

# ==========================================
# CẤU HÌNH THÔNG SỐ CRAWLER
# ==========================================
INPUT_FILE = "./txt_files/products-01.txt"
OUTPUT_DIR = "./output_data"
BATCH_SIZE = 1000
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12
DELAY_BETWEEN_REQUESTS = 1
PROXY = os.getenv("TIKI_PROXY") or None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tiki.vn/",
    "sec-ch-ua": ('"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}

HTML_TAG_REGEX = re.compile(r"<[^>]+>")


def clean_description(raw_html: Optional[str]) -> str:
    """Xóa bỏ thẻ HTML, giải mã thực thể và chuẩn hóa khoảng trắng."""
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = HTML_TAG_REGEX.sub(" ", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join([line for line in lines if line])


def fetch_product_detail(
    session: requests.Session,
    product_id: str,
) -> Optional[Dict[str, Any]]:
    url = f"https://api.tiki.vn/product-detail/api/v1/products/{product_id}"
    last_error_reason = "Unknown Error"
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None

    event_logger.info(f"Start fetching ID {product_id}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Tạm dừng giữa các request để tránh spam server
            if DELAY_BETWEEN_REQUESTS > 0:
                time.sleep(DELAY_BETWEEN_REQUESTS)

            response = session.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                proxies=proxies,
            )

            # 1. Trả về thành công
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as parse_error:
                    raw_html = response.text
                    is_html = "<html" in raw_html[:1000].lower()
                    last_error_reason = (
                        "Blocked HTML response" if is_html else "Invalid JSON response"
                    )
                    event_logger.warning(
                        f"ID {product_id} nhận response không phải JSON"
                        f" ({type(parse_error).__name__}); retrying"
                        f" ({attempt}/{MAX_RETRIES})"
                    )
                    time.sleep(float(2**attempt))
                    continue

                images = []
                if "images" in data and isinstance(data["images"], list):
                    for img in data["images"]:
                        if isinstance(img, dict):
                            img_url = (
                                img.get("base_url")
                                or img.get("large_url")
                                or img.get("url")
                            )
                            if img_url:
                                images.append(img_url)

                event_logger.info(
                    f"✅ Successfully fetched ID {product_id} on attempt {attempt}"
                )
                success_logger.info(f"{product_id},SUCCESS")

                return {
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "url_key": data.get("url_key"),
                    "price": data.get("price"),
                    "description": clean_description(data.get("description")),
                    "images": images,
                }

            # 2. Sản phẩm không tồn tại / đã xóa
            elif response.status_code in (404, 410):
                reason = f"Product not found (HTTP {response.status_code})"
                event_logger.warning(f"Skipping ID {product_id} - {reason}")
                error_logger.error(f"{product_id},{reason}")
                return None

            # 3. Rate Limit (HTTP 429)
            elif response.status_code == 429:
                last_error_reason = "Rate-limited (HTTP 429)"
                retry_after = response.headers.get("Retry-After")
                try:
                    backoff_seconds = (
                        float(10) if retry_after is None else float(retry_after)
                    )
                except (TypeError, ValueError):
                    backoff_seconds = float(2**attempt)

                event_logger.warning(
                    f"⚠️ ID {product_id} dính 429. Nghỉ {backoff_seconds}s trước khi"
                    " thử lại."
                )
                time.sleep(backoff_seconds)
                continue

            # 4. Lỗi Server 5xx hoặc các mã HTTP khác
            else:
                last_error_reason = f"Server Error (HTTP {response.status_code})"
                event_logger.warning(
                    f"ID {product_id} failed with HTTP {response.status_code}. Retrying"
                    f" ({attempt}/{MAX_RETRIES})"
                )
                time.sleep(1)

        except (requests.exceptions.RequestException, TimeoutError) as e:
            error_name = type(e).__name__
            last_error_reason = f"Network/Timeout Error ({error_name})"
            if attempt < MAX_RETRIES:
                event_logger.warning(
                    f"ID {product_id} encountered {error_name}. Retrying"
                    f" ({attempt}/{MAX_RETRIES})"
                )
                time.sleep(1)
            else:
                break

        except Exception as e:
            reason = f"Unexpected Error: {str(e)}"
            event_logger.error(
                f"ID {product_id} encountered a critical error: {reason}"
            )
            error_logger.error(f"{product_id},{reason}")
            return None

    # Ghi nhận thất bại sau tất cả các lần retry
    final_reason = (
        f"Failed after {MAX_RETRIES} attempts - Final error: {last_error_reason}"
    )
    event_logger.error(f"❌ ID {product_id} FAILED: {final_reason}")
    error_logger.error(f"{product_id},{final_reason}")
    return None


def process_batch(
    session: requests.Session,
    batch_ids: List[str],
    batch_index: int,
    progress_bar: tqdm,
) -> None:
    """Xử lý tuần tự danh sách ID trong batch và ghi ra file JSON."""
    file_path = os.path.join(OUTPUT_DIR, f"tiki_products_part_{batch_index:04d}.json")

    if os.path.exists(file_path):
        progress_bar.update(len(batch_ids))
        return

    results = []
    for pid in batch_ids:
        res = fetch_product_detail(session, pid)
        if res is not None:
            results.append(res)
        progress_bar.update(1)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(INPUT_FILE):
        print(
            f"Lỗi: Không tìm thấy file {INPUT_FILE}. Vui lòng kiểm tra lại đường"
            " dẫn."
        )
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        product_ids = [line.strip() for line in f if line.strip()]

    product_ids = list(dict.fromkeys(product_ids))
    total_ids = len(product_ids)
    print(f"Tổng số lượng sản phẩm cần crawl: {total_ids:,}")

    batches = [product_ids[i : i + BATCH_SIZE] for i in range(0, total_ids, BATCH_SIZE)]
    print(f"Tổng số file JSON dự kiến: {len(batches)}")

    pbar = tqdm(total=total_ids, desc="Tiến độ cào dữ liệu", unit="sp")

    # Tái sử dụng TCP connection pool thông qua Session
    with requests.Session() as session:
        for index, batch in enumerate(batches, start=1):
            process_batch(session, batch, index, pbar)

    pbar.close()
    print("\n✅ Hoàn tất tải dữ liệu sản phẩm Tiki!")


if __name__ == "__main__":
    main()
