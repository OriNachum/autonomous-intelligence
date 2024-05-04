import socket
import time

class FaceExpressionEmitter:
    def __init__(self, socket_file='/tmp/eventsocket'):
        self.socket_file = socket_file
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
    def connect(self):
        try:
            self.sock.connect(self.socket_file)
            return True
        except FileNotFoundError:
            print(f"Error: The socket file '{self.socket_file}' was not found.")
            return False
    def emit_expression(self, feeling, talking):
        event_data = json.dumps({
            "event_type": "draw_face",
            "timestamp": time.time(),
            "data": {
                "feeling": feeling,
                "talking": talking,
            }
        })
        self.sock.sendall(event_data.encode('utf-8'))

if "__main__" == __name__:
    # Usage
    emitter = FaceExpressionEmitter()
    success = emitter.connect()
    if (success):
        emitter.emit_events()
    else:
        print("Start server first")
