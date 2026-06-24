"""Live eye mouse debug — preview face mesh, detect blinks, optionally control mouse."""
import argparse
import cv2
import mediapipe as mp
import numpy as np
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mediapipe_models", "face_landmarker.task")


parser = argparse.ArgumentParser()
parser.add_argument("--preview", action="store_true", help="Preview only; does not move the mouse")
parser.add_argument("--control", action="store_true", help="Enable mouse control")
args = parser.parse_args()

if args.control:
    print("[EYE] control mode enabled — starting full EyeController")
    from engine.camera_control.eye_controller import EyeController
    import threading
    stop_evt = threading.Event()
    ctrl = EyeController(stop_event=stop_evt)
    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()
    sys.exit(0)

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
if not cap.isOpened():
    print("[EYE] preview_failed reason=no_camera")
    sys.exit(0)

options = vision.FaceLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False,
)
landmarker = vision.FaceLandmarker.create_from_options(options)
frame_timestamp = 0


def calculate_ear(eye_landmarks):
    v1, v2 = eye_landmarks[1], eye_landmarks[5]
    h1, h3 = eye_landmarks[0], eye_landmarks[3]
    vert = ((v1.x - v2.x) ** 2 + (v1.y - v2.y) ** 2) ** 0.5
    horz = ((h1.x - h3.x) ** 2 + (h1.y - h3.y) ** 2) ** 0.5
    if horz == 0:
        return 1.0
    return vert / horz


BLINK_THRESHOLD = 0.2
print(f"[EYE] preview mode — blink threshold={BLINK_THRESHOLD}")
print(f"[EYE] press 'q' to quit")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_timestamp += 1
    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_img, frame_timestamp)
    frame_h, frame_w, _ = frame.shape

    if result.face_landmarks:
        landmarks = result.face_landmarks[0]

        left_eye = [landmarks[i] for i in [33, 160, 158, 133, 153, 144]]
        ear = calculate_ear(left_eye)

        nose_tip = landmarks[1]
        nose_x, nose_y = int(nose_tip.x * frame_w), int(nose_tip.y * frame_h)
        cv2.circle(frame, (nose_x, nose_y), 5, (0, 255, 0), -1)

        for idx in [168, 175, 195, 197]:
            lm = landmarks[idx]
            x, y = int(lm.x * frame_w), int(lm.y * frame_h)
            cv2.circle(frame, (x, y), 2, (255, 0, 0), -1)

        eye_color = (0, 255, 0) if ear > BLINK_THRESHOLD else (0, 0, 255)
        blink_text = "BLINK" if ear < BLINK_THRESHOLD else "open"
        cv2.putText(frame, f"EAR: {ear:.3f} ({blink_text})", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, eye_color, 2)
        cv2.putText(frame, f"Gaze: ({nose_tip.x:.3f}, {nose_tip.y:.3f})",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        for id, landmark in enumerate(landmarks[474:478]):
            x = int(landmark.x * frame_w)
            y = int(landmark.y * frame_h)
            cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)
    else:
        cv2.putText(frame, "No face detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Eye Mouse Debug", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

landmarker.close()
cap.release()
cv2.destroyAllWindows()
print("[EYE] debug ended")
