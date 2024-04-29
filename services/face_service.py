import pygame
import sys
import math
import random

# Init pygame
pygame.init()

# Sceen settings
screen_width, screen_height = 600,400
screen = pygame.display.set_mode((screen_width, screen_height))
pygame.display.set_caption("Dynamic Face")

# Colros
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)


# Face settings
face_center = (screen_width // 2, screen_height // 2)
face_radius = 100

# Eye settings
eye_offset_x, eye_offset_y = 40, 40

eyes = {
    'happy': { 'size': (40, 30), 'color': GREEN, 'shape': { 'type': 'arc', 'angle': 30 } },
    'normal': { 'size': (30, 20), 'color': BLUE, 'shape': { 'type': 'ellipse', 'angle': 0 } },
    'angry': { 'size': (30, 30) , 'color': RED, 'shape': { 'type':'line', 'angle': 45 } }
}

# Mouth settings
#mouth_happy = { 'width': 100, 'height': 40, 'start_angle': 160, 'stop_angle': 20}
mouth_angry = { 'width': 100, 'height': 40, 'start_angle': 20, 'stop_angle': 160}
mouth_happy = { 'width': 100, 'height': 20, 'start_angle': 200, 'stop_angle': 340}
current_mouth = mouth_happy

mouths = {
    'happy': mouth_happy,
    'angry': mouth_angry,
}
   
def draw_face(expression, talking = False):
    # Clear screen
    screen.fill(WHITE)

    # Draw face
    pygame.draw.circle(screen, BLACK, face_center, face_radius, 2)

    # Draw eyes
    if expression in eyes.keys():
        eye = eyes[expression]
        eye_size = eye['size']
        eye_color = eye['color']
        eye_shape = eye['shape']
        left_eye_rect = [face_center[0] - eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
        right_eye_rect = [face_center[0] + eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
        if eye_shape['type'] == 'ellipse':
            angle_left = math.radians(eye_shape['angle'])
            angle_right = math.radians(180 - eye_shape['angle'])
            pygame.draw.ellipse(screen, eye_color, left_eye_rect, eye_shape['angle'])
            pygame.draw.ellipse(screen, eye_color, right_eye_rect, 180 - eye_shape['angle'] )
        elif eye_shape['type'] == 'arc':
            angle_left = math.radians(eye_shape['angle'])
            angle_right = math.radians(180 - eye_shape['angle'])
            pygame.draw.arc(screen, eye_color, left_eye_rect, angle_left, angle_right, 2)
            pygame.draw.arc(screen, eye_color, right_eye_rect, angle_left, angle_right, 2)
        elif eye_shape['type'] == 'line':
            angle_left = math.radians(eye_shape['angle'])
            angle_right = math.radians(180 - eye_shape['angle'])
            #print(math.pow(eye_size[0], 2), math.pow(eye_size[1],2))
            eye_size_rect = eye_size
            eye_size = (math.sqrt(math.pow(eye_size[0], 2) + math.pow(eye_size[1], 2)))
            #print(eye_size)
            end_left_x = (eye_size * math.sin(angle_left)) + int(left_eye_rect[0])
            end_left_y = (eye_size * math.cos(angle_left)) + int(left_eye_rect[1])
            end_right_x = (eye_size * math.sin(angle_right)) + int(right_eye_rect[0])
            end_right_y = (eye_size * math.cos(angle_right)) + int(right_eye_rect[1])
            pygame.draw.line(screen, eye_color, (int(left_eye_rect[0]), int(left_eye_rect[1] - eye_size_rect[1]//2)), (end_left_x, end_left_y + - eye_size_rect[1]//2), 2)
            pygame.draw.line(screen, eye_color, (int(right_eye_rect[0]), int(right_eye_rect[1] + eye_size_rect[1]//2)), (end_right_x, end_right_y - - eye_size_rect[1]//2), 2)

    else:
        eye = None



    # Draw mouth
    if expression in mouths.keys():
        mouth = mouths[expression]
        mouth_rect = [face_center[0] - mouth['width']//2, face_center[1] + eye_offset_y, mouth['width'], mouth['height']]
        start_angle = math.radians(mouth['start_angle']) if not talking else 0
        stop_angle = math.radians(mouth['stop_angle']) if not talking else 2 * math.pi
        if (talking):
            pygame.draw.ellipse(screen, BLACK, mouth_rect)
        else:
            pygame.draw.arc(screen, BLACK, mouth_rect, start_angle, stop_angle, 2)
    else:
        mouth = None
        start_pos = (face_center[0] - 50, face_center[1] + 50)
        end_pos = (face_center[0] + 50, face_center[1] + 50)
        if (talking):
            mouth_rect = [start_pos[0], end_pos[1]-12.5, 100, 25]
            pygame.draw.ellipse(screen, BLACK, mouth_rect)
        else:
            pygame.draw.line(screen, BLACK, start_pos, end_pos)

    # Update display
    pygame.display.flip()

# Main loop
if "__main__" == __name__:
    running = True
    expression = "normal"
    talking = False
    while running:
        talking = not talking
        pygame.time.wait(random.randrange(1, 6)*50)

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    expression = 'happy'
                elif event.key == pygame.K_a:
                    expression = 'angry'
                elif event.key == pygame.K_n:
                    expression = 'normal'
                if event.key == pygame.K_q:
                    running = False


        draw_face(expression, talking)

    pygame.quit()
    sys.exit()
