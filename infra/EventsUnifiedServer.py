import asyncio
import logging
from MessageBroker import MessageBroker
from UnixSocketServer import UnixSocketServer
from WebSocketServer import WebSocketServer
from SystemHealth import SystemHealth

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
