import pygame
import sys
import math

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
    'happy': { 'size': (40, 30), 'color': GREEN },
    'normal': { 'size': (30, 20), 'color': BLUE },
    'sad': { 'size': (30, 15), 'color': RED }
}

# Mouth settings
#mouth_happy = { 'width': 100, 'height': 40, 'start_angle': 160, 'stop_angle': 20}
mouth_sad = { 'width': 100, 'height': 40, 'start_angle': 20, 'stop_angle': 160}
mouth_happy = { 'width': 100, 'height': 20, 'start_angle': 200, 'stop_angle': 340}
current_mouth = mouth_happy

mouths = {
    'happy': mouth_happy,
    'sad': mouth_sad,
}

def draw_face(expression):
    # Clear screen
    screen.fill(WHITE)

    # Draw face
    pygame.draw.circle(screen, BLACK, face_center, face_radius, 2)

    # Draw eyes
    if expression in eyes.keys():
        eye = eyes[expression]
        eye_size = eye['size']
        eye_color = eye['color']
        left_eye_rect = [face_center[0] - eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
        right_eye_rect = [face_center[0] + eye_offset_x - eye_size[0]//2, face_center[1] - eye_offset_y, *eye_size]
        pygame.draw.ellipse(screen, eye_color, left_eye_rect)
        pygame.draw.ellipse(screen, eye_color, right_eye_rect)
    else:
        eye = None



    # Draw mouth
    if expression in mouths.keys():
        mouth = mouths[expression]
        mouth_rect = [face_center[0] - mouth['width']//2, face_center[1] + eye_offset_y, mouth['width'], mouth['height']]
        start_angle = math.radians(mouth['start_angle'])
        stop_angle = math.radians(mouth['stop_angle'])
        pygame.draw.arc(screen, BLACK, mouth_rect, start_angle, stop_angle, 2)
    else:
        mouth = None
        start_pos = (face_center[0] - 50, face_center[1] + 50)
        end_pos = (face_center[0] + 50, face_center[1] + 50)
        pygame.draw.line(screen, BLACK, start_pos, end_pos)


    # Update display
    pygame.display.flip()

# Main loop
running = True
expression = "normal"
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_h:
                expression = 'happy'
            elif event.key == pygame.K_s:
                expression = 'sad'
            elif event.key == pygame.K_n:
                expression = 'normal'
            if event.key == pygame.K_q:
                running = False


    draw_face(expression)

pygame.quit()
sys.exit()
