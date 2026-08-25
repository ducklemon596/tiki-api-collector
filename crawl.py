import os
import re
import html
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from tqdm.asyncio import tqdm
import ujson as json

INPUT_FILE = "./txt_files/products-01.txt"
OUTPUT_DIR = "./output_data"
BATCH_SIZE = 1000
CONCURRENCY_LIMIT = 40
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12

# Headers giả lập trình duyệt
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

    # 1. Thay thế các thẻ ngắt dòng bằng ký tự newline thực tế
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    # 2. Xoá tất cả thẻ HTML còn lại
    text = HTML_TAG_REGEX.sub(" ", text)
    # 3. Decode HTML entities (&nbsp; -> khoảng trắng, &#39; -> '...)
    text = html.unescape(text)
    # 4. Chuẩn hoá khoảng trắng
    lines = [line.strip() for line in text.split("\n")]
    cleaned_text = "\n".join([line for line in lines if line])
    return cleaned_text


async def fetch_product_detail(
    session: aiohttp.ClientSession, product_id: str, semaphore: asyncio.Semaphore
) -> Optional[Dict[str, Any]]:
    """
    Gọi API Tiki lấy chi tiết sản phẩm bất đồng bộ kèm cơ chế Retry.
    """
    url = f"https://api.tiki.vn/product-detail/api/v1/products/{product_id}"

    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.get(
                    url,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:
                    # Success
                    if response.status == 200:
                        data = await response.json(loads=json.loads)

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

                        return {
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "url_key": data.get("url_key"),
                            "price": data.get("price"),
                            "description": clean_description(data.get("description")),
                            "images": images,
                        }

                    # Non-exist / Deleted
                    elif response.status in (404, 410):
                        return None

                    # Rate-limit
                    elif response.status == 429:
                        wait_time = attempt * 2
                        await asyncio.sleep(wait_time)

                    else:
                        await asyncio.sleep(1)

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1)
                else:
                    return None
            except Exception:
                return None

        return None


async def process_batch(
    session: aiohttp.ClientSession,
    batch_ids: List[str],
    batch_index: int,
    semaphore: asyncio.Semaphore,
    progress_bar: tqdm,
) -> None:
    """
    Thu thập dữ liệu cho 1 batch (1000 sp) và lưu ra file JSON.
    """
    file_path = os.path.join(OUTPUT_DIR, f"tiki_products_part_{batch_index:04d}.json")

    if os.path.exists(file_path):
        progress_bar.update(len(batch_ids))
        return

    tasks = [fetch_product_detail(session, pid, semaphore) for pid in batch_ids]

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

    async with aiohttp.ClientSession(connector=connector) as session:
        for index, batch in enumerate(batches, start=1):
            await process_batch(session, batch, index, semaphore, pbar)

    pbar.close()
    print("\n✅ Hoàn tất tải dữ liệu 200k sản phẩm Tiki!")


if __name__ == "__main__":
    # Tối ưu hóa event loop trên Windows nếu cần
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
