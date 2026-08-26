import asyncio
import random


class RateLimiter:

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

        self.interval = 1.0 / rate
        self.lock = asyncio.Lock()
        self.condition = asyncio.Condition(self.lock)
        self.last_request = 0.0
        self.blocked_until = 0.0
        self.jitter_min = jitter_min
        self.jitter_max = jitter_max

    async def wait(self):
        """Wait for the global backoff, rate interval, and a random jitter."""
        loop = asyncio.get_running_loop()

        while True:
            async with self.condition:
                now = loop.time()
                blocked_for = self.blocked_until - now
                interval_for = self.interval - (now - self.last_request)
                delay = max(blocked_for, interval_for, 0.0)

                if delay == 0:
                    delay = random.uniform(self.jitter_min, self.jitter_max)
                    self.last_request = now + delay
                    break

                # Do not hold the lock while sleeping. apply_backoff() can
                # extend the deadline and wake all waiting workers.
                try:
                    await asyncio.wait_for(self.condition.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

        await asyncio.sleep(delay)

    async def apply_backoff(self, duration: float):
        """Extend the shared backoff deadline and notify every worker."""
        if duration <= 0:
            return

        async with self.condition:
            target_time = asyncio.get_running_loop().time() + duration
            if target_time > self.blocked_until:
                self.blocked_until = target_time
                self.condition.notify_all()
