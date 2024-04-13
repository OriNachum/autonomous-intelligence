import asyncio
import websockets

# TODO add SSL
class WebSocketClient:
    def __init__(self, vision_server_ip_location="./batch/output/nmap_output.txt"):
        self.vision_server_ip_location = vision_server_ip_location
        self.base_ip = self.locate_server()
        self.SECRET_KEY="your_secret_key"

    def locate_server(self):
        # Open the file in read mode
        with open(self.vision_server_ip_location, 'r') as file:
            # Read the first line
            first_line = file.readline()
            first_line = first_line if first_line != "" else '192.168.1.101'
            first_line = first_line.replace('%0a', '').replace('\n', "")
        return first_line

    async def setup_websocket_client(self):
        # Construct the URL for the FastAPI server
        uri = f"ws://{self.base_ip}:8765"
        print(uri)
        async with websockets.connect(uri) as websocket:
            messages = [f"{self.SECRET_KEY}Client pi:  Hello, server! #1", f"{self.SECRET_KEY}Client pi:  Hello, server! #2", f"{self.SECRET_KEY}Client pi:  Hello, server! #3"]
            for message in messages:
                await websocket.send(message)
                await asyncio.sleep(2)
            
            async for message in websocket:
                print(f"Received: {message}")
    
    def start_client(self):
        print("starting")
        asyncio.get_event_loop().run_until_complete(self.setup_websocket_client())
        asyncio.get_event_loop().run_forever()
        print("running")
            
if __name__ == "__main__":
    # Test the FaceDetector class
    wsc = WebSocketClient()
    wsc.start_client()
    
