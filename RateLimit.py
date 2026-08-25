import asyncio


class RateLimiter:

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.lock = asyncio.Lock()
        self.last_request = 0.0
        self.blocked_until = 0.0  # Mốc thời gian dừng toàn bộ hệ thống

    async def wait(self):
        async with self.lock:
            now = asyncio.get_running_loop().time()

            # 1. Nếu hệ thống đang dính Global Backoff, chờ đến khi hết hạn
            if now < self.blocked_until:
                await asyncio.sleep(self.blocked_until - now)
                now = asyncio.get_running_loop().time()

            # 2. Điều phối tốc độ (rate limit) thông thường
            wait_time = self.interval - (now - self.last_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self.last_request = asyncio.get_running_loop().time()

    async def apply_backoff(self, duration: float):
        """Kích hoạt dừng toàn bộ hệ thống trong `duration` giây."""
        async with self.lock:
            now = asyncio.get_running_loop().time()
            target_time = now + duration
            # Chỉ kéo dài thêm nếu thời gian phạt mới lớn hơn mốc hiện có
            if target_time > self.blocked_until:
                self.blocked_until = target_time
