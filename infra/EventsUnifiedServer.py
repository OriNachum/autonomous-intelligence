import asyncio
import websockets
import json
import os
import socket
import logging

# ---------------------------
# Message and Broker Classes
# ---------------------------
class Message:
    def __init__(self, msg_type, sender, destination, payload, priority=0):
        self.msg_type = msg_type
        self.sender = sender
        self.destination = destination
        self.payload = payload
        self.priority = priority

    def to_json(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def from_json(data):
        try:
            dict_obj = json.loads(data)
            return Message(
                dict_obj.get('msg_type'),
                dict_obj.get('sender'),
                dict_obj.get('destination'),
                dict_obj.get('payload'),
                dict_obj.get('priority', 0)
            )
        except Exception as e:
            logging.error(f"Failed to parse message: {e}")
            return None

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

# ---------------------------
# Local Communication (Unix Sockets)
# ---------------------------
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

# ---------------------------
# Network Communication (WebSockets)
# ---------------------------
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

# ---------------------------
# System Health Monitoring
# ---------------------------
class SystemHealth:
    def __init__(self, broker: MessageBroker):
        self.broker = broker

    async def monitor(self):
        while True:
            # A simplistic health check: log number of subscriptions
            count = sum(len(queues) for queues in self.broker.subscribers.values())
            logging.info(f"System Health: {count} active subscriptions.")
            await asyncio.sleep(10)  # Adjust the interval as needed

# ---------------------------
# Main Execution: Starting Servers & Monitoring
# ---------------------------
async def main():
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    
    broker = MessageBroker()
    unix_server = UnixSocketServer(broker)
    ws_server = WebSocketServer(broker)
    health_monitor = SystemHealth(broker)

    # Running all components concurrently
    tasks = [
        asyncio.create_task(unix_server.start()),
        asyncio.create_task(ws_server.start()),
        asyncio.create_task(health_monitor.monitor())
    ]
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down the event system.")
