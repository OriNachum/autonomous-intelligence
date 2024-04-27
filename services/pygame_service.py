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

# Face settings
face_center = (screen_width // 2, screen_height // 2)
face_radius = 100

# Eye settings
eye_radius = 15
eye_offset_x, eye_offset_y = 30, 40

# Mouth settings
mouth_default = { 'top': 10, 'bottom': 20, 'start_angle': -20, 'stop_angle': 20}
xmouth_happy = { 'top': 15, 'bottom': 30, 'start_angle': -20, 'stop_angle': 20}
mouth_sad = { 'top': 15, 'bottom': -10, 'start_angle': 20, 'stop_angle': -20}
current_mouth = mouth_default

def draw_face(expression):
    # Clear screen
    screen.fill(WHITE)

    # Draw face
    pygame.draw.circle(screen, BLACK, face_center, face_radius, 2)

    # Draw eyes
    left_eye_center = (face_center[0] - eye_offset_x, face_center[1] - eye_offset_y)
    right_eye_center = (face_center[0] + eye_offset_x, face_center[1] - eye_offset_y)
    pygame.draw.circle(screen, BLACK, left_eye_center, eye_radius)
    pygame.draw.circle(screen, BLACK, right_eye_center, eye_radius)

    # Draw mouth
    if expression == 'happy':
        mouth = mouth_happy
    elif expression == 'sad':
        mouth = mouth_sad
    else:
        mouth = mouth_default

    start_pos = (face_center[0] - mouth['top'], face_center[1] + eye_offset_y)
    end_pos = (face_center[0] + mouth['top'], face_center[1] + eye_offset_y)
    pygame.draw.arc(screen, BLACK, [face_center[0] - 50, face_center[1], 100, 60],
                    math.radians(mouth['start_angle']), math.radians(mouth['stop_angle']), 2)

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
