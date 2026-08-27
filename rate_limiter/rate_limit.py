import asyncio
import random


class RateLimiter:
    """
    Trình giới hạn tốc độ request cho asyncio, hỗ trợ Jitter (độ trễ ngẫu nhiên)
    và Global Backoff (đóng băng toàn cục khi dính WAF/429).
    """

    def __init__(
        self,
        rate: float,
        jitter_min: float = 0.05,
        jitter_max: float = 0.25,
    ):
        if rate <= 0:
            raise ValueError("rate must be greater than zero")
        if jitter_min < 0 or jitter_max < jitter_min:
            raise ValueError("invalid jitter range")

        self.interval = 1.0 / rate  # Khoảng cách thời gian bắt buộc giữa 2 request
        self.lock = asyncio.Lock()

        # Biến điều kiện giúp các task có thể ngủ và gọi nhau
        self.condition = asyncio.Condition(self.lock)

        self.last_request = 0.0  # Mốc thời gian hoàn thành của request gần nhất
        self.blocked_until = 0.0  # Mốc thời gian hệ thống bị khóa (phạt WAF)

        self.jitter_min = jitter_min
        self.jitter_max = jitter_max

    async def wait(self):
        """Hàm chờ: Tính toán thời gian Rate limit, Backoff và ngẫu nhiên hóa Jitter."""
        loop = asyncio.get_running_loop()

        # Vòng lặp để đảm bảo nếu bị đánh thức giữa chừng, task sẽ phải tính lại thời gian
        while True:
            async with self.condition:
                now = loop.time()

                # Tính toán xem có đang trong thời gian Global Backoff không
                blocked_for = self.blocked_until - now

                # Tính toán xem đã đủ khoảng cách thời gian giữa 2 request chưa
                interval_for = self.interval - (now - self.last_request)

                # Lấy khoảng thời gian phải chờ dài nhất (nếu < 0 thì delay = 0)
                delay = max(blocked_for, interval_for, 0.0)

                # NẾU KHÔNG PHẢI CHỜ NỮA
                if delay == 0:
                    delay = random.uniform(self.jitter_min, self.jitter_max)
                    self.last_request = now + delay
                    break

                # NẾU PHẢI CHỜ
                # Tạm nhả khóa ra và đi ngủ để các task khác còn vào kiểm tra
                # Sẽ thức dậy khi: có lệnh notify_all() hoặc hết thời gian timeout (delay)
                try:
                    await asyncio.wait_for(self.condition.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    # Nếu hết thời gian timeout -> Chạy bình thường.
                    # Vòng lặp while quay lại tính toán (lúc này delay sẽ = 0)
                    pass

        # Ngủ nốt phần thời gian ngẫu nhiên (Jitter)
        # Ngủ ở ngoài khối 'async with' để không làm kẹt các luồng khác
        await asyncio.sleep(delay)

    async def apply_backoff(self, duration: float):
        """
        Cập nhật timeout mới và gọi TẤT CẢ các task đang ngủ dậy (để thông báo các task khác rằng thời gian chờ đã bị tăng lên).
        Được gọi khi một request bất kỳ dính lỗi 429 hoặc bị WAF trả về HTML.
        """
        if duration <= 0:
            return

        async with self.condition:
            target_time = asyncio.get_running_loop().time() + duration

            # Chỉ cập nhật nếu án phạt mới lâu hơn án phạt hiện tại
            if target_time > self.blocked_until:
                self.blocked_until = target_time

                # Đánh thức toàn bộ các task đang ngủ trong hàm `wait_for` dậy.
                # Bắt các task này quay lại vòng lặp while để thông báo thời gian chờ vừa bị tăng lên.
                self.condition.notify_all()
