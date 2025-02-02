
import asyncio
import logging
import websockets
from Message import Message
from MessageBroker import MessageBroker

class WebSocketServer:
    def __init__(self, broker: MessageBroker, host='localhost', port=8765):
        self.broker = broker
        self.host = host
        self.port = port
        self.connected_clients = set()

    async def handler(self, websocket, path):
        self.connected_clients.add(websocket)
        logging.info(f"WebSocket client connected: {websocket.remote_address}")
        try:
            async for message_data in websocket:
                message = Message.from_json(message_data)
                if message:
                    await self.broker.publish(message)
        except Exception as e:
            logging.error(f"WebSocket connection error: {e}")
        finally:
            self.connected_clients.remove(websocket)
            logging.info(f"WebSocket client disconnected: {websocket.remote_address}")

    async def start(self):
        server = await websockets.serve(self.handler, self.host, self.port)
        logging.info(f"WebSocket server started at ws://{self.host}:{self.port}")
        await server.wait_closed()

    async def broadcast(self, message: Message):
        if self.connected_clients:
            data = message.to_json()
            await asyncio.wait([client.send(data) for client in self.connected_clients])