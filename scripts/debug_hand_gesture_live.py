"""Live hand gesture debug — preview landmarks, detect gestures, optionally control mouse."""
import argparse
import cv2
import mediapipe as mp
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_utils, drawing_styles

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mediapipe_models", "hand_landmarker.task")


parser = argparse.ArgumentParser()
parser.add_argument("--preview", action="store_true", help="Preview only; does not move the mouse")
parser.add_argument("--control", action="store_true", help="Enable mouse control")
args = parser.parse_args()

if args.control:
    print("[HAND] control mode enabled — starting full HandController")
    from engine.camera_control.hand_controller import HandController
    import threading
    stop_evt = threading.Event()
    ctrl = HandController(stop_event=stop_evt)
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
    print("[CAMERA] preview_failed reason=no_camera")
    sys.exit(0)

options = vision.HandLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=vision.RunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.65,
    min_tracking_confidence=0.65,
)
landmarker = vision.HandLandmarker.create_from_options(options)
frame_timestamp = 0


def get_distance(a, b):
    return np.hypot(b[0] - a[0], b[1] - a[1])


SCROLL_THRESH = 0.09
PINCH_THRESH = 0.035
RIGHT_THRESH = 0.04

print(f"[HAND] preview mode — press 'q' to quit")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_timestamp += 1
    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_img, frame_timestamp)

    landmark_list = []
    if result.hand_landmarks:
        hand_landmarks = result.hand_landmarks[0]
        drawing_utils.draw_landmarks(
            frame, hand_landmarks,
            drawing_styles.get_default_hand_connections_style(),
        )
        for lm in hand_landmarks:
            landmark_list.append((lm.x, lm.y))

        if len(landmark_list) >= 21:
            idx_tip = landmark_list[8]
            idx_mid = landmark_list[12]
            thumb = landmark_list[4]
            pinky = landmark_list[20]
            idx_mid_dist = get_distance(idx_tip, idx_mid)
            idx_thumb_dist = get_distance(thumb, idx_tip)
            mid_thumb_dist = get_distance(thumb, idx_mid)
            thumb_pinky_dist = get_distance(thumb, pinky)

            cv2.putText(frame, f"idx-mid: {idx_mid_dist:.3f} (scroll<{SCROLL_THRESH})",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(frame, f"idx-thumb: {idx_thumb_dist:.3f} (pinch<{PINCH_THRESH})",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(frame, f"mid-thumb: {mid_thumb_dist:.3f} (Rclick<{RIGHT_THRESH})",
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(frame, f"thumb-pinky: {thumb_pinky_dist:.3f}", (10, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(frame, f"index pos: ({idx_tip[0]:.3f}, {idx_tip[1]:.3f})",
                        (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            is_scroll = idx_mid_dist < SCROLL_THRESH and idx_thumb_dist > 0.05
            is_pinch = idx_thumb_dist < PINCH_THRESH
            is_right = mid_thumb_dist < RIGHT_THRESH

            if is_scroll:
                status = "SCROLL"
                color = (0, 255, 255)
            elif is_pinch:
                status = "PINCH (left click)"
                color = (0, 255, 0)
            elif is_right:
                status = "MID-PINCH (right click)"
                color = (255, 0, 255)
            else:
                status = "POINTING"
                color = (0, 200, 255)

            cv2.putText(frame, f"Gesture: {status}", (10, 190),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    else:
        cv2.putText(frame, "No hand detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Hand Gesture Debug", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

landmarker.close()
cap.release()
cv2.destroyAllWindows()
print("[HAND] debug ended")
