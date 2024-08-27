import pygame
import sys
import math
import random
import asyncio
import socket
import os
import json
import time
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Init websocket client
class FaceService:
    def __init__(self):
        self.base_ip = "127.0.0.10"
        self.SECRET_KEY = "your_secret_key"
        self.socket_file = './uds_socket'

        # Init pygame
        pygame.init()
        logger.info("Pygame initialized")

        # Screen settings
        self.screen_width, self.screen_height = 600, 400
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Dynamic Face")
        logger.info(f"Screen set up with dimensions: {self.screen_width}x{self.screen_height}")

        # Colors
        self.BLACK = (0, 0, 0)
        self.WHITE = (255, 255, 255)
        self.BLUE = (0, 0, 255)
        self.GREEN = (0, 255, 0)
        self.RED = (255, 0, 0)

        # Face settings
        self.face_center = (self.screen_width // 2, self.screen_height // 2)
        self.face_radius = 100

        # Eye settings
        self.eye_offset_x, self.eye_offset_y = 40, 40

        self.eyes = {
            'happy': {'size': (40, 30), 'color': self.GREEN, 'shape': {'type': 'arc', 'angle': 30}},
            'normal': {'size': (30, 20), 'color': self.BLUE, 'shape': {'type': 'ellipse', 'angle': 0}},
            'angry': {'size': (30, 30), 'color': self.RED, 'shape': {'type': 'line', 'angle': 45}}
        }

        # Mouth settings
        self.current_mouth = None
        self.mouths = {
            'angry': {'width': 100, 'height': 40, 'start_angle': 20, 'stop_angle': 160},
            'happy': {'width': 100, 'height': 20, 'start_angle': 200, 'stop_angle': 340},
        }

        logger.debug("FaceService initialized with all settings")

    def start_client(self):
        logger.info("Starting face client")
        self.draw_face('normal')

        # Delete the socket file if it already exists
        if os.path.exists(self.socket_file):
            os.remove(self.socket_file)
            logger.debug(f"Removed existing socket file: {self.socket_file}")

        # Connect to the Unix domain socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_file)
        sock.listen(1)
        logger.info(f"Listening on Unix domain socket: {self.socket_file}")

        connection, client_address = sock.accept()
        logger.info(f"Accepted connection from {client_address}")

        try:
            while True:
                logger.debug("Waiting to receive data")
                data = connection.recv(1024)
                if not data:
                    logger.warning("No data received, breaking the loop")
                    break
                data = data.decode('utf-8')
                logger.info(f"Received data: {data}")
                event = json.loads(data)
                keys = event['data'].keys()
                if 'expression' in keys:
                    expression = event['data']['expression']
                    logger.info(f"Updating expression to: {expression}")
                    talking = event['data'].get('talking', False)
                    self.draw_face(expression, talking)
                logger.debug("Sending acknowledgement")
                connection.sendall('ack'.encode('utf-8'))
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}", exc_info=True)
        finally:
            logger.info("Closing connection")
            connection.close()

    def draw_face(self, expression, talking=False):
        logger.info(f"Drawing face with expression: {expression}, talking: {talking}")
        screen = self.screen
        face_center = self.face_center
        face_radius = self.face_radius
        eye_offset_x = self.eye_offset_x
        eye_offset_y = self.eye_offset_y

        # Clear screen
        screen.fill(self.WHITE)

        # Draw face
        pygame.draw.circle(screen, self.BLACK, face_center, face_radius, 2)

        # Draw eyes
        if expression in self.eyes.keys():
            eye = self.eyes[expression]
            eye_size = eye['size']
            eye_color = eye['color']
            eye_shape = eye['shape']
            left_eye_rect = [face_center[0] - eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
            right_eye_rect = [face_center[0] + eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
            
            if eye_shape['type'] == 'ellipse':
                angle_left = math.radians(eye_shape['angle'])
                angle_right = math.radians(180 - eye_shape['angle'])
                pygame.draw.ellipse(screen, eye_color, left_eye_rect, eye_shape['angle'])
                pygame.draw.ellipse(screen, eye_color, right_eye_rect, 180 - eye_shape['angle'])
            elif eye_shape['type'] == 'arc':
                angle_left = math.radians(eye_shape['angle'])
                angle_right = math.radians(180 - eye_shape['angle'])
                pygame.draw.arc(screen, eye_color, left_eye_rect, angle_left, angle_right, 2)
                pygame.draw.arc(screen, eye_color, right_eye_rect, angle_left, angle_right, 2)
            elif eye_shape['type'] == 'line':
                angle_left = math.radians(eye_shape['angle'])
                angle_right = math.radians(180 - eye_shape['angle'])
                eye_size_rect = eye_size
                eye_size = (math.sqrt(math.pow(eye_size[0], 2) + math.pow(eye_size[1], 2)))
                end_left_x = (eye_size * math.sin(angle_left)) + int(left_eye_rect[0])
                end_left_y = (eye_size * math.cos(angle_left)) + int(left_eye_rect[1])
                end_right_x = (eye_size * math.sin(angle_right)) + int(right_eye_rect[0])
                end_right_y = (eye_size * math.cos(angle_right)) + int(right_eye_rect[1])
                pygame.draw.line(screen, eye_color, (int(left_eye_rect[0]), int(left_eye_rect[1] - eye_size_rect[1]//2)), (end_left_x, end_left_y + - eye_size_rect[1]//2), 2)
                pygame.draw.line(screen, eye_color, (int(right_eye_rect[0]), int(right_eye_rect[1] + eye_size_rect[1]//2)), (end_right_x, end_right_y - - eye_size_rect[1]//2), 2)
        else:
            logger.warning(f"Unknown eye expression: {expression}")

        # Draw mouth
        if expression in self.mouths.keys():
            mouth = self.mouths[expression]
            mouth_rect = [face_center[0] - mouth['width']//2, face_center[1] + eye_offset_y, mouth['width'], mouth['height']]
            start_angle = math.radians(mouth['start_angle']) if not talking else 0
            stop_angle = math.radians(mouth['stop_angle']) if not talking else 2 * math.pi
            if talking:
                pygame.draw.ellipse(screen, self.BLACK, mouth_rect)
            else:
                pygame.draw.arc(screen, self.BLACK, mouth_rect, start_angle, stop_angle, 2)
        else:
            logger.warning(f"Unknown mouth expression: {expression}")
            start_pos = (face_center[0] - 50, face_center[1] + 50)
            end_pos = (face_center[0] + 50, face_center[1] + 50)
            if talking:
                mouth_rect = [start_pos[0], end_pos[1]-12.5, 100, 25]
                pygame.draw.ellipse(screen, self.BLACK, mouth_rect)
            else:
                pygame.draw.line(screen, self.BLACK, start_pos, end_pos)

        # Update display
        pygame.display.flip()
        logger.debug("Face drawing completed")

# Main loop
if "__main__" == __name__:
    face_service = FaceService()    
    demo = sys.argv[1] if len(sys.argv) > 1 else ""
    running = True
    expression = "normal"
    talking = False

    if demo == "demo":
        logger.info("Running in demo mode")
        while running:
            talking = not talking
            pygame.time.wait(random.randrange(1, 6)*50)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    logger.info("Quit event received")
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_h:
                        expression = 'happy'
                    elif event.key == pygame.K_a:
                        expression = 'angry'
                    elif event.key == pygame.K_n:
                        expression = 'normal'
                    if event.key == pygame.K_q:
                        running = False
                    logger.info(f"Key pressed: {event.key}, new expression: {expression}")

            face_service.draw_face(expression, talking)
    else:
        logger.info("Starting face service client")
        face_service.start_client()

    logger.info("Quitting Pygame and exiting")
    pygame.quit()
    sys.exit()
