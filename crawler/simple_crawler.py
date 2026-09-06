import time
import random
from config import (
    INPUT_FILE,
    INPUT_DIR,
    OUTPUT_DIR,
    NOT_FOUND_FILE,
    HEADERS,
    DELAY,
    REQUEST_TIMEOUT,
    MAX_WAF_RETRIES,
    WAF_RETRY_DELAY,
    SAVE_INTERVAL,
    BATCH_SIZE,
)

from utils import (
    get_resume_state,
    load_and_batch_ids,
    save_batch_json,
    fetch_product_data,
)
from logger import event_logger, not_found_logger, write_disk_logger

INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    batches, total_ids = load_and_batch_ids(INPUT_FILE, BATCH_SIZE)
    if not batches:
        print(
            f"⚠️ LỖI: Không tìm thấy file hoặc file trống tại đường dẫn: {INPUT_FILE}"
        )
        return

    start_batch_idx, fetched_data, initial_pending = get_resume_state(
        OUTPUT_DIR, NOT_FOUND_FILE, batches
    )

    print(f"Tổng số ID cần xử lý: {total_ids:,}")
    print(f"Bắt đầu chạy từ Batch thứ: {start_batch_idx + 1}")

    for batch_idx in range(start_batch_idx, len(batches)):
        batch_num = batch_idx + 1

        if batch_idx == start_batch_idx:
            # Nếu là batch đầu tiên lúc bật máy -> Dùng data cũ và danh sách ID đã lọc
            batch_results = fetched_data
            pending_ids = initial_pending
        else:
            # Từ batch sau trở đi -> Mảng trắng tinh, bốc thẳng 1000 ID mới ra cào
            batch_results = []
            pending_ids = batches[batch_idx]

        if not pending_ids:
            continue

        event_logger.info(
            f"--- BẮT ĐẦU BATCH {batch_num:04d} ({len(pending_ids)} ID cần fetch tiếp) ---"
        )
        new_success_count = 0
        pending_save_ids = []

        # 4. Fetch từng ID
        for pid in pending_ids:
            product_data = fetch_product_data(
                product_id=pid,
                batch_num=batch_num,
                event_logger=event_logger,
                not_found_logger=not_found_logger,
                waf_retry_delay=WAF_RETRY_DELAY,
                max_waf_retries=MAX_WAF_RETRIES,
                headers=HEADERS,
                request_timeout=REQUEST_TIMEOUT,
                delay=DELAY,
            )

            if product_data:
                batch_results.append(product_data)
                new_success_count += 1
                pending_save_ids.append(str(pid))

            # Lưu JSON mỗi 10 request thành công
            if new_success_count > 0 and new_success_count % SAVE_INTERVAL == 0:
                save_batch_json(batch_results, batch_num)

                msg_saved = f"{', '.join(pending_save_ids)}"
                write_disk_logger.info(msg_saved)
                pending_save_ids.clear()

                event_logger.info(
                    f"Đã lưu JSON (Batch {batch_num:04d}) với {len(batch_results)} SP."
                )

            time.sleep(
                random.uniform(DELAY * 0.7, DELAY * 1.3)
            )  # Thêm random delay để tránh bị WAF

        # Lưu lần cuối khi hoàn thành toàn bộ batch
        if new_success_count > 0:
            save_batch_json(batch_results, batch_num)

            msg_saved = f"{', '.join(pending_save_ids)}"
            write_disk_logger.info(msg_saved)

            event_logger.info(
                f"--- HOÀN THÀNH BATCH {batch_num:04d} (Tổng thực tế: {len(batch_results)} SP) ---"
            )

    print("\n🎉 HOÀN TẤT TOÀN BỘ QUÁ TRÌNH CÀO DỮ LIỆU!")
    event_logger.info("HOÀN TẤT TOÀN BỘ QUÁ TRÌNH CÀO DỮ LIỆU!")


if __name__ == "__main__":
    main()
