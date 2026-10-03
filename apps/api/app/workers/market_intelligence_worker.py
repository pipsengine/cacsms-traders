import asyncio
import logging

log = logging.getLogger(__name__)


class MarketIntelligenceWorker:
    def __init__(self, run_cycle, interval: int = 300):
        self.run_cycle = run_cycle
        self.interval = interval
        self.running = False

    async def start(self):
        self.running = True
        log.info("Market intelligence worker started (interval=%ss)", self.interval)
        while self.running:
            try:
                await self.run_cycle()
            except Exception:
                log.exception("Market intelligence cycle failed")
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False
