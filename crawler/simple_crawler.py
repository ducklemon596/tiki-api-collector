import time
from pathlib import Path
import requests
import ujson as json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
INPUT_FILE = INPUT_DIR / "products-01.txt"
OUTPUT_FILE = OUTPUT_DIR / "products.json"
REQUEST_TIMEOUT = 10
DELAY = 1  # Giây giữa các request

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://tiki.vn/",
}


def main():
    # Đọc danh sách ID
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        product_ids = [line.strip() for line in f if line.strip()]

    results = []

    # Chạy tuần tự từng sản phẩm
    for index, pid in enumerate(product_ids, start=1):
        url = f"https://api.tiki.vn/product-detail/api/v1/products/{pid}"
        print(f"[{index}/{len(product_ids)}] Fetching ID: {pid}...")

        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                try:
                    data = response.json()
                    results.append(data)
                    print(f"-> OK: {data.get('name', 'No name')}")
                except Exception:
                    print("-> BỊ CHẶN (HTML/WAF): Không thể parse JSON")
            else:
                print(f"-> LỖI HTTP: {response.status_code}")

        except Exception as e:
            print(f"-> LỖI MẠNG: {e}")

        time.sleep(DELAY)


if __name__ == "__main__":
    main()
