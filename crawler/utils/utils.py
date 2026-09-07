import logging
import re
from typing import Optional
import html
from pathlib import Path
import ujson as json
import requests
import time
from config import HTML_TAG_REGEX, OUTPUT_DIR


def load_and_batch_ids(
    file_path: Path, batch_size: int = 1000
) -> tuple[list[list[int]], int]:
    """Đọc file ID, loại bỏ trùng lặp, validate kiểu số và chia thành các batch.

    Trả về danh sách rỗng nếu không tìm thấy file hoặc file không có dữ liệu
    hợp lệ.

    Args:
        file_path (Path): Đường dẫn tới file chứa danh sách ID.
        batch_size (int): Kích thước mỗi batch.

    Returns:
        tuple[list[list[int]], int]: Tuple chứa danh sách các batch và tổng số ID hợp lệ.
    """
    if not file_path.exists():
        return [], 0

    valid_ids = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and cleaned.isdigit():
                valid_ids.append(int(cleaned))

    # Loại bỏ ID trùng lặp nhưng vẫn giữ nguyên thứ tự xuất hiện ban đầu
    unique_ids = list(dict.fromkeys(valid_ids))

    if not unique_ids:
        return [], 0

    return [
        unique_ids[i : i + batch_size] for i in range(0, len(unique_ids), batch_size)
    ], len(unique_ids)


def get_resume_state(
    output_dir: Path,
    not_found_file: Path,
    batches: list[list[int]],
    start_batch: int = 1,
    end_batch: Optional[int] = None,
) -> tuple[int, list[dict], list[int]]:
    """Xác định batch cần chạy tiếp và danh sách ID còn thiếu (trong trường hợp resume) bằng cách đọc file batch gần nhất.
    Args:
        output_dir (Path): Thư mục chứa các file batch.
        not_found_file (Path): Đường dẫn tới file chứa các ID 404.
        batches (list[list[int]]): Danh sách các batch.
        start_batch (int): Batch bắt đầu (1-based index).
        end_batch (Optional[int]): Batch kết thúc (1-based index). Nếu None, sẽ chạy đến batch cuối cùng.
    Returns:
        batch_idx (int): Chỉ số batch cần chạy tiếp (0-based index).
        existing_data (list[dict]): Danh sách dữ liệu đã fetch thành công từ file batch gần nhất.
        pending_ids (list[int]): Danh sách ID còn thiếu cần fetch tiếp."""

    if end_batch is None:
        end_batch = len(batches)

    # Chỉ lấy các file json nằm trong phạm vi [start_batch, end_batch]
    valid_files = []
    for f in output_dir.glob("tiki_batch_*.json"):
        try:
            b_num = int(f.stem.split("_")[-1])
            if start_batch <= b_num <= end_batch:
                valid_files.append(f)
        except ValueError:
            continue

    batch_files = sorted(valid_files)

    # Nếu không có file batch nào, bắt đầu từ batch đầu tiên
    if not batch_files:
        start_idx = start_batch - 1
        if start_idx >= len(batches):
            return len(batches), [], []
        return start_idx, [], batches[start_idx]

    # Lấy file batch mới nhất
    latest_file = batch_files[-1]
    latest_batch_num = int(latest_file.stem.split("_")[-1])
    batch_idx = latest_batch_num - 1

    # Quét qua file batch mới nhất để xác định các ID đã fetch thành công (không tốn thời gian nhiều so với request delay)
    fetched_ids = set()
    existing_data = []
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            fetched_ids.update(
                int(item["id"]) for item in existing_data if "id" in item
            )
    except Exception:
        pass

    # Đọc file not_found_404.log để loại bỏ các ID đã được xác nhận là không tồn tại
    if not_found_file.exists():
        with open(not_found_file, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                if cleaned:
                    pid_str = cleaned.split("|")[-1].strip()
                    if pid_str.isdigit():
                        fetched_ids.add(int(pid_str))

    expected_ids = batches[batch_idx]
    # Lấy danh sách ID còn thiếu (chưa fetch thành công và chưa bị 404)
    pending_ids = [pid for pid in expected_ids if pid not in fetched_ids]

    if not pending_ids:
        next_idx = batch_idx + 1
        if next_idx < len(batches) and next_idx < end_batch:
            return next_idx, [], batches[next_idx]
        return next_idx, [], []
    else:
        return batch_idx, existing_data, pending_ids


def clean_html(raw_html: Optional[str]) -> str:
    """Loại bỏ các thẻ HTML và chuyển đổi các ký tự HTML entities thành ký tự thông thường"""
    if not raw_html:
        return ""
    text = re.sub(r"<(br|p|div|li)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = HTML_TAG_REGEX.sub(" ", text)
    return html.unescape(text).strip()


def extract_product_info(raw_data: dict) -> dict:
    """Trích xuất thông tin sản phẩm từ dữ liệu thô
    Args:
        raw_data (dict): Dữ liệu thô của sản phẩm

    Returns:
        dict: Thông tin sản phẩm đã được trích xuất, gồm các trường: id, name, url_key, price, description, images
    """
    images = []
    if isinstance(raw_data.get("images"), list):
        for img in raw_data["images"]:
            if isinstance(img, dict):
                img_url = img.get("base_url") or img.get("large_url") or img.get("url")
                if img_url:
                    images.append(img_url)

    return {
        "id": raw_data.get("id"),
        "name": raw_data.get("name"),
        "url_key": raw_data.get("url_key"),
        "price": raw_data.get("price"),
        "description": clean_html(raw_data.get("description")),
        "images": images,
    }


def fetch_product_data(
    cloudflare_worker_url: str,
    product_id: int,
    batch_num: int,
    event_logger: logging.Logger,
    not_found_logger: logging.Logger,
    waf_retry_delay: float,
    max_waf_retries: int,
    headers: dict,
    request_timeout: int,
    delay: float,
) -> Optional[dict]:
    """Fetch dữ liệu sản phẩm từ API Tiki dựa trên product_id.
    Args:
        cloudflare_worker_url (str): URL của Cloudflare Worker để bypass WAF.
        product_id (int): ID của sản phẩm cần fetch.
        batch_num (int): Số thứ tự của batch.
        event_logger: Logger để ghi lại các sự kiện.
        not_found_logger: Logger để ghi lại các ID không tìm thấy.
        waf_retry_delay (float): Thời gian chờ giữa các lần thử lại khi bị chặn bởi WAF.
        max_waf_retries (int): Số lần thử lại tối đa khi bị chặn bởi WAF.
        headers: Headers cho yêu cầu HTTP.
        request_timeout (int): Thời gian chờ tối đa cho yêu cầu HTTP.
        new_success_count (int): Số lượng sản phẩm fetch thành công mới.
        delay (float): Thời gian chờ giữa các yêu cầu HTTP.
    Returns:
        Optional[dict]: Dữ liệu sản phẩm nếu fetch thành công, None nếu không tìm thấy hoặc lỗi.
    """

    url = f"https://{cloudflare_worker_url}/?url=https://api.tiki.vn/product-detail/api/v1/products/{product_id}"
    msg_start = f"Batch {batch_num:04d} | Fetching ID {product_id}..."
    print(msg_start, end=" ")
    event_logger.info(msg_start)

    waf_retries = 0
    success = False

    current_waf_delay = waf_retry_delay

    while not success:
        try:
            response = requests.get(url, headers=headers, timeout=request_timeout)

            if response.status_code == 200:
                try:
                    raw_data = response.json()
                    parsed_data = extract_product_info(raw_data)

                    msg_ok = f"-> OK ({parsed_data.get('name', '')[:25]}...)"
                    print(msg_ok)
                    event_logger.info(f"ID {product_id} {msg_ok}")

                    return parsed_data
                except Exception:
                    # Dính WAF, trả về HTML
                    waf_retries += 1

                    if waf_retries > max_waf_retries:
                        msg_ban = "-> IP bị blocked. Dừng request 60 phút trước khi thử lại..."
                        print(msg_ban)
                        event_logger.critical(f"ID {product_id} {msg_ban}")

                        time.sleep(3600)
                        waf_retries = 0
                        current_waf_delay = (
                            waf_retry_delay  # Reset lại thời gian chờ cơ bản
                        )
                        continue
                    else:
                        msg_waf = f"-> 🚨 Chặn WAF. Nghỉ {current_waf_delay}s. Retry {waf_retries}/{max_waf_retries}"
                        print(msg_waf)
                        event_logger.warning(f"ID {product_id} {msg_waf}")

                        time.sleep(current_waf_delay)
                        current_waf_delay *= 2
                        continue

            elif response.status_code in (404, 410):
                msg_404 = "-> 404 Not Found"
                print(msg_404)
                event_logger.info(f"ID {product_id} {msg_404}")
                not_found_logger.info(product_id)
                return None

            else:
                msg_err = f"-> Lỗi HTTP {response.status_code}"
                print(msg_err)
                event_logger.error(f"ID {product_id} {msg_err}")
                time.sleep(delay)
                # Lỗi HTTP thông thường (500, 502) cũng coi như cần chờ
                waf_retries += 1

        except Exception as e:
            msg_net = f"-> LỖI MẠNG: {type(e).__name__}"
            print(msg_net)
            event_logger.error(f"ID {product_id} {msg_net}")
            time.sleep(delay)
            waf_retries += 1

    return None


def save_batch_json(batch_data: list, batch_index: int):
    """Ghi đè/cập nhật danh sách JSON của một batch"""
    file_path = OUTPUT_DIR / f"tiki_batch_{batch_index:04d}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(batch_data, f, ensure_ascii=False, indent=2)
