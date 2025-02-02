
import asyncio
import logging
from MessageBroker import MessageBroker

class SystemHealth:
    def __init__(self, broker: MessageBroker):
        self.broker = broker

    async def monitor(self):
        while True:
            # A simplistic health check: log number of subscriptions
            count = sum(len(queues) for queues in self.broker.subscribers.values())
            logging.info(f"System Health: {count} active subscriptions.")
            await asyncio.sleep(10)  # Adjust the interval as needed