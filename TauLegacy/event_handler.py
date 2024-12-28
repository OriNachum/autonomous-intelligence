import os
import socket
import selectors
import logging
from config import logger  # Ensure logger is imported
from speech_processing import archive_speech
socket_path = "./sockets/tau_hearing_socket"


sel = selectors.DefaultSelector()

def setup_socket():
    logger.info(f"Setting up socket at {socket_path}")
    if os.path.exists(socket_path):
        os.remove(socket_path)
        logger.debug(f"Removed existing socket file: {socket_path}")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(1)
    sock.setblocking(False)  # Set socket to non-blocking mode
    sel.register(sock, selectors.EVENT_READ, accept)
    logger.info("Socket setup complete")
    return sock

def accept(sock):
    conn, addr = sock.accept()
    logger.info(f"Accepted connection from {addr}")
    sel.register(conn, selectors.EVENT_READ, read)

def read(conn):
    data = conn.recv(1024)
    if data:
        logger.debug(f"Received data: {data.decode('utf-8')[:20]}...")  # Log first 50 chars
        return data.decode('utf-8')
    else:
        logger.info("Connection closed")
        sel.unregister(conn)
        conn.close()
        return None

def handle_events():
    logger.debug("Handling events")
    while True:
        events = sel.select()
        for key, mask in events:
            callback = key.data
            data = callback(key.fileobj)
            if data:
                logger.debug(f"Received data: {data[:50]}...")  # Log first 50 chars
                if "Speech started" in data:
                    logger.info("Speech started event received. Stopping ongoing speech output.")
                    # Add code here to stop ongoing speech output
                    # For example: speech_queue.stop_current()
                    archive_speech()
        
                    # Now wait for the "Speech stopped" event
                    continue

                elif "Speech stopped" in data:
                    logger.info("Speech stopped event received. Returning input.")
                    # Extract the actual speech content
                    speech_content = data.split("Transcript:", 1)[1].strip()
                    return speech_content  # Return the speech content

                else:
                    logger.debug("Received other event, continuing to listen.")
                    continue  # Continue listening for relevant events
    return None  # This line should never be reached

