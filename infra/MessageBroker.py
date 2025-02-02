
import logging
import asyncio
from Message import Message

class MessageBroker:
    def __init__(self):
        # Subscribers: mapping destination -> list of asyncio queues
        self.subscribers = {}

    def subscribe(self, destination, queue):
        if destination not in self.subscribers:
            self.subscribers[destination] = []
        self.subscribers[destination].append(queue)
        logging.info(f"Subscriber added for destination '{destination}'.")

    async def publish(self, message: Message):
        if not message:
            return
        # If a destination is set, deliver to that subscriber's queues
        delivered = False
        if message.destination in self.subscribers:
            for q in self.subscribers[message.destination]:
                await q.put(message)
            delivered = True
        # Broadcast to all if no specific destination is provided
        if not delivered:
            for queues in self.subscribers.values():
                for q in queues:
                    await q.put(message)
        logging.info(f"Published message from {message.sender} to {message.destination} with type {message.msg_type}")