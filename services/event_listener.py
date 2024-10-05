import socket
import selectors
import logging

# Set up the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventListener:
    """
    Handles connection to an external Unix Domain Socket to listen for events.
    """

    def __init__(self, socket_path, selector, callback):
        """
        Initializes the EventListener.

        :param socket_path: Path to the Unix Domain Socket to connect.
        :param selector: The selectors.DefaultSelector instance to register events.
        :param callback: Function to call when data is received.
        """
        self.socket_path = socket_path
        self.selector = selector
        self.callback = callback
        self.client_socket = None
        self.last_event = None  # Store the last event data
        self._connect()

    def _connect(self):
        """Establishes a non-blocking connection to the Unix Domain Socket."""
        logger.info(f"Connecting to external Unix Domain Socket at {self.socket_path}")
        self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.client_socket.connect(self.socket_path)
            logger.info(f"Connected to Unix Domain Socket at {self.socket_path}")
        except FileNotFoundError:
            logger.error(f"Socket path '{self.socket_path}' does not exist. Please ensure the server is running.")
            self.client_socket = None
            return
        except ConnectionRefusedError:
            logger.error("Could not connect to the server. Please make sure the server is running and accessible.")
            self.client_socket = None
            return

        self.client_socket.setblocking(False)
        self.selector.register(self.client_socket, selectors.EVENT_READ, self._read)

    def _read(self, conn):
        """Callback method to handle incoming data."""
        try:
            data = conn.recv(1024)
            if data:
                decoded_data = data.decode('utf-8').strip()
                logger.debug(f"Received external event data: {decoded_data[:50]}...")
                self.last_event = decoded_data  # Store the last event data
                self.callback(decoded_data)
            else:
                logger.info("External server disconnected")
                self.selector.unregister(conn)
                conn.close()
        except BlockingIOError:
            # No data available
            pass
        except Exception as e:
            logger.error(f"Error reading from external socket: {e}", exc_info=True)
            self.selector.unregister(conn)
            conn.close()

    def get_last_event(self):
        """Returns the last received event data."""
        return self.last_event

    def close(self):
        """Closes the client socket and unregisters it from the selector."""
        if self.client_socket:
            logger.info("Closing external event listener socket")
            self.selector.unregister(self.client_socket)
            self.client_socket.close()
            self.client_socket = None
