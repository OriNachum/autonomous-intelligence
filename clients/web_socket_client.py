import asyncio
import websockets
import json

# TODO add SSL

class WebSocketClient:
    def __init__(self, vision_server_ip_location="./batch/output/nmap_output.txt"):
        self.vision_server_ip_location = vision_server_ip_location
        self.base_ip = self.locate_server()
        self.SECRET_KEY = "your_secret_key"
        self.websocket = None
        self.task = None

    def locate_server(self):
        # Open the file in read mode
        with open(self.vision_server_ip_location, 'r') as file:
            # Read the first line
            first_line = file.readline()
            first_line = first_line if first_line != "" else '192.168.1.101'
            first_line = first_line.replace('%0a', '').replace('\n', "")
        return first_line

    async def consume_events(self):
        async with websockets.connect(f"ws://{self.base_ip}:8765") as websocket:
            self.websocket = websocket
            while True:
                message = await websocket.recv()
                event = json.loads(message)
                if event["event_type"] == "what_i_see":
                    print("Received 'what_i_see' event:")
                    print(event)
                elif event["event_type"] == "recognized_object":
                    print("Received 'recognized_object' event:")
                    print(event)
                else:
                    print(f"Received message: {message}")

    def start_client(self):
        print("starting")
        self.task = asyncio.get_event_loop().create_task(self.consume_events())
        asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    # Test the WebSocketClient class
    wsc = WebSocketClient()
    wsc.start_client()