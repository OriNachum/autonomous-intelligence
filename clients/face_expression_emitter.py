import socket
import time
import json
import os
import sys

class FaceExpressionEmitter:
    def __init__(self, socket_file='./uds_socket'):
        self.connection = None
        self.client_address = None
        self.socket_file = socket_file
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        #try:
        #    os.unlink(self.socket_file)
        #except OSError:
        #    if os.path.exists(self.socket_file):
        #        raise RunTimeError('Unable to remove the existing socket file.') 

    def connect(self):
        try:
            self.sock.connect(self.socket_file)
            #self.sock.bind(self.socket_file)
            #self.sock.listen(1)
            return True
        except FileNotFoundError:
            print(f"Error: The socket file '{self.socket_file}' was not found.")
            return False

    def emit_expression(self, feeling, talking):

        event_data = json.dumps({
            "event_type": "draw_face",
            "timestamp": time.time(),
            "data": {
                "expression": feeling,
                "talking": talking,
            }
        })
        #if self.client_address is None:
        #    connection, client_address = self.sock.accept()
        #    self.connection = connection
        #    self.client_adress = client_address
        try:
            encoded_event = event_data.encode('utf-8')
            self.sock.sendall(encoded_event)
            time.sleep(1)
            ack = self.sock.recv(1024)
            decoded_ack = ack.decode('utf-8')
            #print(f'Received ack: {decoded_ack}')
        except:
            if self.notified_error is None or self.notified_error == False:
                print("Warning: no face (face_expression_emitter)")
                self.notified_error = True

if "__main__" == __name__:
    # Usage
    expression = sys.argv[1] if len(sys.argv) > 1 else "angry"
    emitter = FaceExpressionEmitter()
    success = emitter.connect()
    if (success):
        talking = True
        while True:
            print("emitting new expression")
            emitter.emit_expression(expression, talking)
            expression = input("happy, angry, neutral")
            talking = not talking
    else:
        print("Start server first")
