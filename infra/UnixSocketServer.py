
import asyncio
import os
import logging
from Message import Message
from MessageBroker import MessageBroker

class UnixSocketServer:
    def __init__(self, broker: MessageBroker, socket_path='/tmp/ai_event_system.sock'):
        self.broker = broker
        self.socket_path = socket_path
        self.server = None

    async def handle_client(self, reader, writer):
        try:
            data = await reader.read(1024)
            if data:
                message = Message.from_json(data.decode())
                if message:
                    await self.broker.publish(message)
        except Exception as e:
            logging.error(f"Error handling Unix socket client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        # Clean up any existing socket file
        try:
            os.remove(self.socket_path)
        except FileNotFoundError:
            pass
        self.server = await asyncio.start_unix_server(self.handle_client, path=self.socket_path)
        logging.info(f"Unix socket server started at {self.socket_path}")
        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
            logging.info("Unix socket server stopped.")