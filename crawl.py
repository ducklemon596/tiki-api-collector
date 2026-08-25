import os
import re
import html
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from tqdm.asyncio import tqdm
import ujson as json
import logging
import os

from RateLimit import RateLimiter

# ==========================================
# CẤU HÌNH LOGGING ĐA LUỒNG
# ==========================================

# 1. Logger tổng hợp mọi sự kiện (Event History)
event_logger = logging.getLogger("event_logger")
event_logger.setLevel(logging.INFO)

event_handler = logging.FileHandler("events_history.log", encoding="utf-8")
event_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)

event_logger.addHandler(event_handler)

# 2. Logger chỉ ghi ID lỗi ra file CSV
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

# 3. Logger chỉ ghi ID thành công ra file CSV
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

INPUT_FILE = "./txt_files/products-01.txt"
OUTPUT_DIR = "./output_data"
BATCH_SIZE = 1000
CONCURRENCY_LIMIT = 1
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12
API_RATE_LIMIT = 150

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tiki.vn/",
}

# Regex bóc tách HTML tags để tối ưu tốc độ so với BeautifulSoup
HTML_TAG_REGEX = re.compile(r"<[^>]+>")
EXTRA_WHITESPACE_REGEX = re.compile(r"\n\s*\n")


def clean_description(raw_html: Optional[str]) -> str:
    """
    Chuẩn hoá nội dung description:
    - Loại bỏ toàn bộ thẻ HTML
    - Giải mã các thực thể HTML (&amp;, &nbsp;, ...)
    - Xoá khoảng trắng thừa và dòng trống liên tiếp
    """
    if not raw_html:
        return ""

    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = HTML_TAG_REGEX.sub(" ", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.split("\n")]
    cleaned_text = "\n".join([line for line in lines if line])
    return cleaned_text


from typing import Any, Dict, Optional
import aiohttp


async def fetch_product_detail(
    session: aiohttp.ClientSession,
    product_id: str,
    semaphore: asyncio.Semaphore,
    rate_limiter: RateLimiter,
) -> Optional[Dict[str, Any]]:
    url = f"https://api.tiki.vn/product-detail/api/v1/products/{product_id}"
    last_error_reason = "Unknown Error"

    async with semaphore:
        event_logger.info(f"Start fetching ID {product_id}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Kiểm soát tốc độ và kiểm tra Global Backoff trước khi gửi
                await rate_limiter.wait()

                async with session.get(
                    url,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:

                    # 1. Thành công
                    if response.status == 200:
                        try:
                            data = await response.json(
                                loads=json.loads, content_type=None
                            )
                        except Exception as parse_error:
                            raw_html = await response.text()
                            event_logger.error(
                                f"ID {product_id} không phải JSON! Phản hồi từ Tiki: {raw_html}"
                            )
                            raise parse_error

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

                    # 2. Không tồn tại
                    elif response.status in (404, 410):
                        reason = f"Product not found (HTTP {response.status})"
                        event_logger.warning(f"Skipping ID {product_id} - {reason}")
                        error_logger.error(f"{product_id},{reason}")
                        return None

                    # 3. Bị Rate-limit -> KÍCH HOẠT GLOBAL BACKOFF
                    elif response.status == 429:
                        last_error_reason = "Rate-limited (HTTP 429)"

                        # Kiểm tra header Retry-After từ server
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            backoff_seconds = float(retry_after)
                        else:
                            # Exponential backoff: 2s, 4s, 8s,...
                            backoff_seconds = float(2**attempt)

                        event_logger.warning(
                            f"⚠️ ID {product_id} dính 429. Kích hoạt Global Backoff"
                            f" {backoff_seconds}s cho TOÀN BỘ task."
                        )
                        await rate_limiter.apply_backoff(backoff_seconds)
                        continue

                    # 4. Lỗi Server 5xx
                    else:
                        last_error_reason = f"Server Error (HTTP {response.status})"
                        event_logger.warning(
                            f"ID {product_id} failed with HTTP {response.status}. Retrying"
                            f" ({attempt}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(1)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                error_name = type(e).__name__
                last_error_reason = f"Network/Timeout Error ({error_name})"
                if attempt < MAX_RETRIES:
                    event_logger.warning(
                        f"ID {product_id} encountered {error_name}. Retrying"
                        f" ({attempt}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(1)
                else:
                    break

            except Exception as e:
                reason = f"Unexpected Error: {str(e)}"
                event_logger.error(
                    f"ID {product_id} encountered a critical error: {reason}"
                )
                error_logger.error(f"{product_id},{reason}")
                return None

        # Ghi nhận thất bại cuối cùng
        final_reason = (
            f"Failed after {MAX_RETRIES} attempts - Final error: {last_error_reason}"
        )
        event_logger.error(f"❌ ID {product_id} FAILED: {final_reason}")
        error_logger.error(f"{product_id},{final_reason}")
        return None


async def process_batch(
    session: aiohttp.ClientSession,
    batch_ids: List[str],
    batch_index: int,
    semaphore: asyncio.Semaphore,
    progress_bar: tqdm,
    rate_limiter: RateLimiter,
) -> None:
    """
    Thu thập dữ liệu cho 1 batch (1000 sp) và lưu ra file JSON.
    """
    file_path = os.path.join(OUTPUT_DIR, f"tiki_products_part_{batch_index:04d}.json")

    if os.path.exists(file_path):
        progress_bar.update(len(batch_ids))
        return

    tasks = [
        fetch_product_detail(session, pid, semaphore, rate_limiter) for pid in batch_ids
    ]

    results = []
    for coro in asyncio.as_completed(tasks):
        res = await coro
        if res is not None:
            results.append(res)
        progress_bar.update(1)

    # Ghi dữ liệu ra file JSON
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


async def main():
    # 1. Đảm bảo thư mục lưu trữ tồn tại
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 2. Đọc danh sách Product IDs
    if not os.path.exists(INPUT_FILE):
        print(
            f"Lỗi: Không tìm thấy file {INPUT_FILE}. Vui lòng tải file ID về và đặt đúng tên."
        )
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        product_ids = [line.strip() for line in f if line.strip()]

    # Loại bỏ ID trùng lặp
    product_ids = list(dict.fromkeys(product_ids))
    total_ids = len(product_ids)
    print(f"Tổng số lượng sản phẩm cần crawl: {total_ids:,}")

    # 3. Chia thành các batch 1.000 sản phẩm
    batches = [product_ids[i : i + BATCH_SIZE] for i in range(0, total_ids, BATCH_SIZE)]
    print(f"Tổng số file JSON dự kiến: {len(batches)}")

    # 4. Khởi tạo Connection Pool và Semaphore
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY_LIMIT + 10, ttl_dns_cache=300)

    pbar = tqdm(total=total_ids, desc="Tiến độ cào dữ liệu", unit="sp")

    RateLimiter_instance = RateLimiter(rate=API_RATE_LIMIT)  # Tạo instance RateLimiter

    async with aiohttp.ClientSession(connector=connector) as session:
        for index, batch in enumerate(batches, start=1):
            await process_batch(
                session, batch, index, semaphore, pbar, RateLimiter_instance
            )

    pbar.close()
    print("\n✅ Hoàn tất tải dữ liệu 200k sản phẩm Tiki!")


if __name__ == "__main__":
    # Tối ưu hóa event loop trên Windows nếu cần
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
