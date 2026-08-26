import os
import re
import html
import asyncio
import random
from typing import List, Dict, Any, Optional
from tqdm.asyncio import tqdm
import ujson as json
import logging
from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession

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

# ==========================================
# THÔNG SỐ CRAWLER
# ==========================================
INPUT_FILE = "./txt_files/products-01.txt"
OUTPUT_DIR = "./output_data"
BATCH_SIZE = 1000
CONCURRENCY_LIMIT = 5  # Có thể tăng lên 5-10 vì đã dùng curl_cffi + Jitter
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12
API_RATE_LIMIT = 10  # Tốc độ an toàn (request/giây)
PROXY = os.getenv("TIKI_PROXY") or None  # Định dạng: "http://user:pass@ip:port"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tiki.vn/",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}

HTML_TAG_REGEX = re.compile(r"<[^>]+>")


# ==========================================
# CƠ CHẾ RATE LIMITER (GLOBAL BACKOFF + JITTER)
# ==========================================
class RateLimiter:
    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.lock = asyncio.Lock()
        self.last_request = 0.0
        self.blocked_until = 0.0  # Quản lý Global Backoff

    async def wait(self):
        async with self.lock:
            now = asyncio.get_running_loop().time()

            # 1. Xử lý Global Backoff (Nếu bị 429, toàn hệ thống phải chờ)
            if now < self.blocked_until:
                await asyncio.sleep(self.blocked_until - now)
                now = asyncio.get_running_loop().time()

            # 2. Xử lý Rate Limit thông thường
            wait_time = self.interval - (now - self.last_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            # 3. Thêm Full Jitter (Độ trễ ngẫu nhiên 50ms - 250ms để phá vỡ chu kỳ bot)
            jitter = random.uniform(0.05, 0.25)
            await asyncio.sleep(jitter)

            self.last_request = asyncio.get_running_loop().time()

    async def apply_backoff(self, duration: float):
        """Kích hoạt trạng thái chặn toàn cục khi dính lỗi 429/HTML."""
        async with self.lock:
            now = asyncio.get_running_loop().time()
            target_time = now + duration
            if target_time > self.blocked_until:
                self.blocked_until = target_time


def clean_description(raw_html: Optional[str]) -> str:
    """Chuẩn hoá nội dung description"""
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = HTML_TAG_REGEX.sub(" ", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join([line for line in lines if line])


async def fetch_product_detail(
    session: AsyncSession,
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
                # KIỂM SOÁT TỐC ĐỘ LUÔN NẰM TRONG VÒNG LẶP RETRY
                await rate_limiter.wait()

                response = await session.get(
                    url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                    proxy=PROXY,
                    impersonate="chrome124",
                )

                # 1. THÀNH CÔNG
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as parse_error:
                        # WAF TRẢ VỀ HTML (CHẶN IP/BOT)
                        raw_html = response.text
                        is_html = "<html" in raw_html[:1000].lower()

                        last_error_reason = (
                            "Blocked by WAF (HTML Response)"
                            if is_html
                            else "Invalid JSON response"
                        )
                        backoff_time = float(
                            5 * attempt
                        )  # Phạt nặng hơn nếu bị WAF chặn

                        event_logger.warning(
                            f"🚨 ID {product_id} bị WAF chặn (nhận HTML)! Kích hoạt Global Backoff {backoff_time}s. Lần thử: ({attempt}/{MAX_RETRIES})"
                        )
                        await rate_limiter.apply_backoff(backoff_time)
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

                # 2. KHÔNG TỒN TẠI
                elif response.status_code in (404, 410):
                    reason = f"Product not found (HTTP {response.status_code})"
                    event_logger.warning(f"Skipping ID {product_id} - {reason}")
                    error_logger.error(f"{product_id},{reason}")
                    return None

                # 3. RATE LIMIT 429
                elif response.status_code == 429:
                    last_error_reason = "Rate-limited (HTTP 429)"
                    retry_after = response.headers.get("Retry-After")
                    try:
                        backoff_seconds = float(retry_after)
                    except (TypeError, ValueError):
                        backoff_seconds = float(2**attempt)

                    event_logger.warning(
                        f"⚠️ ID {product_id} dính 429. Kích hoạt Global Backoff {backoff_seconds}s cho TOÀN BỘ task."
                    )
                    await rate_limiter.apply_backoff(backoff_seconds)
                    continue

                # 4. SERVER ERROR 5xx
                else:
                    last_error_reason = f"Server Error (HTTP {response.status_code})"
                    event_logger.warning(
                        f"ID {product_id} failed with HTTP {response.status_code}. Retrying ({attempt}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(1)

            except CurlError as e:
                error_name = type(e).__name__
                last_error_reason = f"Network/Curl Error ({error_name})"
                if attempt < MAX_RETRIES:
                    event_logger.warning(
                        f"ID {product_id} encountered {error_name}. Retrying ({attempt}/{MAX_RETRIES})"
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
    session: AsyncSession,
    batch_ids: List[str],
    batch_index: int,
    semaphore: asyncio.Semaphore,
    progress_bar: tqdm,
    rate_limiter: RateLimiter,
) -> None:
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

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(INPUT_FILE):
        print(f"Lỗi: Không tìm thấy file {INPUT_FILE}.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        product_ids = [line.strip() for line in f if line.strip()]

    product_ids = list(dict.fromkeys(product_ids))
    total_ids = len(product_ids)
    print(f"Tổng số lượng sản phẩm cần crawl: {total_ids:,}")

    batches = [product_ids[i : i + BATCH_SIZE] for i in range(0, total_ids, BATCH_SIZE)]
    print(f"Tổng số file JSON dự kiến: {len(batches)}")

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    pbar = tqdm(total=total_ids, desc="Tiến độ cào dữ liệu", unit="sp")

    # Rate Limiter được truyền tham số tốc độ an toàn
    rate_limiter = RateLimiter(rate=API_RATE_LIMIT)

    async with AsyncSession() as session:
        for index, batch in enumerate(batches, start=1):
            await process_batch(session, batch, index, semaphore, pbar, rate_limiter)

    pbar.close()
    print("\n✅ Hoàn tất tải dữ liệu sản phẩm Tiki!")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
