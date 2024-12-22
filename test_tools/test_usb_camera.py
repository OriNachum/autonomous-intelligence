import cv2

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break
    cv2.imshow("Camera feed", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cap.release()
cv.destroyAllWIndows()

