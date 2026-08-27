
# Tiki Product Crawler

Công cụ đọc danh sách mã sản phẩm từ file Excel, gọi Tiki Product Detail API
và lưu dữ liệu sản phẩm thành các file JSON.

API được sử dụng:

```text
https://api.tiki.vn/product-detail/api/v1/products/{product_id}
```

Dữ liệu đầu ra gồm: `id`, `name`, `url_key`, `price`, `description` và `images`.

## 1. Mục đích và luồng xử lý

1. Đặt file Excel (`.xlsx`) vào `data/input/`.
2. Đọc cột đầu tiên của Excel, loại bỏ giá trị rỗng và tạo file `.txt` chứa
	 một product ID trên mỗi dòng.
3. Crawler đọc file `.txt`, loại bỏ ID trùng lặp và chia danh sách thành batch.
4. Mỗi batch được lưu thành một file JSON trong `data/output/`.
5. File JSON đã tồn tại được bỏ qua để có thể tiếp tục sau khi bị gián đoạn.

## 2. Vấn đề gặp phải

Sau một vài request đầu, API có thể vẫn trả HTTP `200` nhưng body là HTML chứa
BytePlus WAF Challenge thay vì JSON. Vì vậy chương trình gặp
`JSONDecodeError` hoặc `Blocked HTML Response`; các lần retry sau đó thường
tiếp tục nhận HTML.

Mở cùng URL bằng Chrome vẫn có thể nhận JSON vì Chrome thực thi JavaScript
challenge và có client identity giống trình duyệt hơn. Các thử nghiệm giảm
concurrency từ `40` xuống `1`, rate từ `150 req/s` xuống `1 req/s`, chạy
tuần tự bằng `requests`, hoặc retry với backoff đều không loại bỏ hoàn toàn
việc bị chặn.

Nguyên nhân có khả năng chính là anti-bot ở tầng nhận diện client:

- TLS fingerprint (JA3/JA4) của Python khác Chrome.
- HTTP client thuần không có JavaScript engine để giải challenge và tạo cookie.
- Cách thương lượng giao thức và HTTP/2 cũng có thể khác trình duyệt thật.

## 3. Cơ chế mode `sync`

Mode `sync` dùng `requests.Session` và xử lý tuần tự từng product ID:

- Tái sử dụng TCP connection pool qua một `Session`.
- Chờ `--delay` giây trước mỗi request để giảm tốc độ gọi API.
- Giới hạn thời gian bằng `--timeout`.
- Retry lỗi mạng, timeout, lỗi server, HTML hoặc JSON không hợp lệ.
- Dùng exponential backoff khi không parse được JSON.
- Với HTTP `429`, đọc `Retry-After`; nếu thiếu thì dùng thời gian chờ dự phòng.
- HTTP `404` và `410` được ghi log và bỏ qua, không retry.

Mode này dễ theo dõi và ít tạo burst request, nhưng tốc độ thấp vì mỗi lúc chỉ
xử lý một request.

## 4. Cơ chế mode `async`

Mode `async` dùng `curl-cffi.AsyncSession` với `impersonate="chrome124"`:

- Tạo nhiều task bất đồng bộ trong mỗi batch.
- `asyncio.Semaphore` giới hạn request đồng thời bằng `--concurrency`.
- `RateLimiter` giới hạn tốc độ toàn cục bằng `--rate-limit`.
- Retry lỗi mạng, curl error, lỗi server, HTTP `429`, HTML và JSON không hợp lệ.
- Global backoff: khi một task gặp `429` hoặc WAF challenge, toàn bộ task phải
	chờ trước khi gửi request tiếp theo.
- Jitter ngẫu nhiên `0.05` đến `0.25` giây giúp các task không gửi đồng thời.
- `curl-cffi` mô phỏng một số đặc điểm Chrome, nhưng không thay thế trình
	duyệt có JavaScript engine.

## 5. Cơ chế cài đặt `RateLimiter`

`RateLimiter` nằm trong `rate_limiter/rate_limit.py` và là module nội bộ,
không cần cài riêng. Dependency `curl-cffi` được khai báo trong
`pyproject.toml`.

Async crawler khởi tạo:

```python
rate_limiter = RateLimiter(rate=10)
```

Với `rate=10`, khoảng cách cơ sở là $1 / 10 = 0.1$ giây giữa hai request.
Trước mỗi request, crawler gọi `await rate_limiter.wait()`. Hàm này dùng
`asyncio.Lock` và `asyncio.Condition` để:

1. Đồng bộ lịch request giữa các task.
2. Chờ đủ khoảng cách rate limit hoặc global backoff.
3. Thêm jitter ngẫu nhiên từ `0.05` đến `0.25` giây.

Khi gặp `429` hoặc WAF challenge, crawler gọi
`await rate_limiter.apply_backoff(seconds)`. Thời điểm `blocked_until` được
dùng chung; chỉ backoff mới dài hơn mới thay thế thời điểm hiện tại và các
task đang chờ sẽ tính toán lại thời gian.

## 6. Cài đặt môi trường

Yêu cầu Python `>= 3.13`. Khuyến nghị dùng `uv`:

```powershell
uv sync
```

Hoặc dùng pip:

```powershell
pip install -e .
```

## 7. Cách chạy chi tiết

### Bước 1: Chuyển Excel thành danh sách ID

Đặt file `.xlsx` vào `data/input/`. Product ID phải nằm ở cột đầu tiên (hiện tại folder đã chứa sẵn file .txt nên không cần chạy bước này):

```powershell
uv run python converter/convert_id.py
```

Mỗi file Excel tạo một file `.txt` tương ứng trong `data/input/`.

### Bước 2: Chạy mode `sync`

```powershell
uv run python main.py --mode sync --input data/input/products-01.txt
```

Ví dụ cấu hình:

```powershell
uv run python main.py --mode sync `
	--input data/input/products-01.txt `
	--output data/output `
	--batch-size 500 `
	--delay 2 `
	--timeout 20 `
	--retries 5
```

### Bước 3: Chạy mode `async`

```powershell
uv run python main.py --mode async --input data/input/products-01.txt
```

Ví dụ cấu hình:

```powershell
uv run python main.py --mode async `
	--input data/input/products-01.txt `
	--output data/output `
	--batch-size 500 `
	--concurrency 5 `
	--rate-limit 10 `
	--timeout 20 `
	--retries 5
```

### Bước 4: Xem tất cả tùy chọn

```powershell
uv run python main.py --help
```

| Tham số | Mặc định | Ý nghĩa |
| --- | ---: | --- |
| `--mode` | `sync` | Chế độ `sync` hoặc `async` |
| `--input` | `data/input/products-01.txt` | File product ID |
| `--output` | `data/output` | Thư mục JSON đầu ra |
| `--batch-size` | `1000` | Số ID trong một file JSON |
| `--delay` | `1` | Delay giữa request sync, tính bằng giây |
| `--concurrency` | `5` | Số request async đồng thời |
| `--rate-limit` | `10` | Rate async, request/giây |
| `--timeout` | `12` | Timeout mỗi request, tính bằng giây |
| `--retries` | `3` | Số lần thử tối đa |
| `--proxy` | Không có | Proxy HTTP/HTTPS/SOCKS5 |

## 8. Proxy và log

Truyền proxy trực tiếp qua CLI:

```powershell
uv run python main.py --mode async `
	--proxy "socks5://user:password@host:port"
```

Hoặc dùng biến môi trường:

```powershell
$env:TIKI_PROXY = "socks5://user:password@host:port"
uv run python main.py --mode async
```

Log sự kiện, thành công và lỗi được ghi trong `logs/`. Response HTML lỗi cũng
được in ra terminal để kiểm tra WAF.

## 9. Lưu ý

- Bắt đầu với concurrency và rate limit thấp.
- Nếu WAF trả HTML liên tục, hãy dừng crawler và chờ trước khi chạy lại.
- Không commit proxy chứa username, password hoặc thông tin nhạy cảm.
- Tuân thủ điều khoản sử dụng của Tiki và giới hạn truy cập phù hợp.
