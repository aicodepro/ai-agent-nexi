import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import json
import pyautogui

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from engine.camera_control.mouse_actions import move_cursor, left_click, set_debug
from engine.camera_control.smoothing import GazeSmoothingFilter

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "mediapipe_models", "face_landmarker.task")

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
if os.getenv("CAMERA_WIDTH"):
    try: CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH"))
    except: pass
if os.getenv("CAMERA_HEIGHT"):
    try: CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT"))
    except: pass
if os.getenv("CAMERA_FPS"):
    try: CAMERA_FPS = int(os.getenv("CAMERA_FPS"))
    except: pass

BLINK_THRESHOLD = 0.2
BLICK_CLICK_COOLDOWN_MS = 700
EYE_SMOOTHING = 0.6
DWELL_CLICK_MS = 1500
DWELL_RADIUS = 30
CAMERA_READ_FAILURE_LIMIT = 3
CAMERA_READ_FAILURE_BACKOFF = 0.1

CALIBRATION_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eye_calibration.json"
)


class EyeController:
    def __init__(self, stop_event: threading.Event, use_gpu: bool = False):
        self._stop_event = stop_event
        self._use_gpu = use_gpu
        self._cap = None
        self._landmarker = None
        es = float(os.getenv("CAMERA_GAZE_SMOOTHING", str(EYE_SMOOTHING)))
        self._gaze_filter = GazeSmoothingFilter(factor=es, deadzone=8.0)
        self._last_blink_time = 0.0
        self._dwell_start = None
        self._last_dwell_pos = None
        self._calibration = self._load_calibration()
        self._blink_enabled = True
        self._dwell_enabled = False
        self._frame_timestamp = 0

    def run(self):
        set_debug(False)
        self._cap = cv2.VideoCapture(0)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

        if self._use_gpu:
            delegate = python.BaseOptions.Delegate.GPU
        else:
            delegate = python.BaseOptions.Delegate.CPU

        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH, delegate=delegate),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        try:
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
        except Exception as e:
            self._stop_event.set()
            self._stop()
            return {
                "ok": False,
                "status": "unavailable",
                "reason": "model_load_failed",
                "detail": f"{type(e).__name__}: {e}",
            }

        screen_w, screen_h = pyautogui.size()
        read_failures = 0

        try:
            while self._cap.isOpened() and not self._stop_event.is_set():
                ret, frame = self._cap.read()
                if not ret:
                    read_failures += 1
                    if read_failures >= CAMERA_READ_FAILURE_LIMIT:
                        self._stop_event.set()
                        print("[EYE] camera_disconnected", flush=True)
                        return {
                            "ok": False,
                            "status": "unavailable",
                            "reason": "camera_disconnected",
                        }
                    self._stop_event.wait(CAMERA_READ_FAILURE_BACKOFF)
                    continue
                read_failures = 0

                self._frame_timestamp += 1
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = self._landmarker.detect_for_video(mp_img, self._frame_timestamp)

                frame_h, frame_w, _ = frame.shape

                if result.face_landmarks:
                    landmarks = result.face_landmarks[0]

                    gaze_x, gaze_y = self._get_gaze_point(landmarks, frame_w, frame_h)
                    screen_x = (gaze_x / frame_w) * screen_w
                    screen_y = (gaze_y / frame_h) * screen_h

                    if self._calibration:
                        screen_x, screen_y = self._apply_calibration(screen_x, screen_y, screen_w, screen_h)

                    smooth_x, smooth_y = self._gaze_filter.update(screen_x, screen_y)
                    move_cursor(int(smooth_x), int(smooth_y))

                    self._check_blink(landmarks, frame)
                    self._check_dwell(smooth_x, smooth_y)

                    for id, landmark in enumerate(landmarks[474:478]):
                        x = int(landmark.x * frame_w)
                        y = int(landmark.y * frame_h)
                        cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)
                else:
                    self._gaze_filter.reset()

                cv2.imshow("Eye Mouse Control", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    break
        except pyautogui.FailSafeException:
            self._stop_event.set()
            print("[EYE] stopped reason=failsafe", flush=True)
            return {"ok": False, "status": "stopped", "reason": "failsafe"}
        finally:
            self._stop()

    def stop(self):
        self._stop_event.set()
        self._stop()

    def _stop(self):
        if self._landmarker:
            self._landmarker.close()
        if self._cap:
            self._cap.release()
        cv2.destroyAllWindows()

    @staticmethod
    def _calculate_ear(eye_landmarks):
        v1 = eye_landmarks[1]
        v2 = eye_landmarks[5]
        h1 = eye_landmarks[0]
        h3 = eye_landmarks[3]
        vert = ((v1.x - v2.x) ** 2 + (v1.y - v2.y) ** 2) ** 0.5
        horz = ((h1.x - h3.x) ** 2 + (h1.y - h3.y) ** 2) ** 0.5
        if horz == 0:
            return 1.0
        return vert / horz

    def _get_gaze_point(self, landmarks, frame_w, frame_h):
        gaze_indices = [1, 4, 5, 6, 7, 8, 9, 10, 168, 175, 195, 197]
        if len(landmarks) <= max(gaze_indices):
            return frame_w / 2, frame_h / 2
        x_sum = 0.0
        y_sum = 0.0
        count = 0
        for idx in gaze_indices:
            lm = landmarks[idx]
            x_sum += lm.x * frame_w
            y_sum += lm.y * frame_h
            count += 1
        if count == 0:
            return frame_w / 2, frame_h / 2
        return x_sum / count, y_sum / count

    def _check_blink(self, landmarks, frame):
        eye_indices = [33, 160, 158, 133, 153, 144]
        if len(landmarks) <= max(eye_indices):
            return
        left_eye = [landmarks[i] for i in eye_indices]
        ear = self._calculate_ear(left_eye)
        now = time.time()
        if ear < BLINK_THRESHOLD and self._blink_enabled:
            if (now - self._last_blink_time) * 1000 > BLICK_CLICK_COOLDOWN_MS:
                print(f"[EYE] blink detected ear={ear:.3f}")
                left_click()
                self._last_blink_time = now

    def _check_dwell(self, x, y):
        if not self._dwell_enabled:
            self._dwell_start = None
            self._last_dwell_pos = None
            return
        if self._last_dwell_pos is not None:
            dx = x - self._last_dwell_pos[0]
            dy = y - self._last_dwell_pos[1]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < DWELL_RADIUS:
                if self._dwell_start is None:
                    self._dwell_start = time.time()
                elif (time.time() - self._dwell_start) * 1000 > DWELL_CLICK_MS:
                    left_click()
                    self._dwell_start = None
                    self._last_dwell_pos = None
                    return
            else:
                self._dwell_start = None
        self._last_dwell_pos = (x, y)

    def _apply_calibration(self, x, y, screen_w, screen_h):
        cx = self._calibration.get("center_x", screen_w / 2)
        cy = self._calibration.get("center_y", screen_h / 2)
        scale_x = self._calibration.get("scale_x", 1.0)
        scale_y = self._calibration.get("scale_y", 1.0)
        cal_x = cx + (x - cx) * scale_x
        cal_y = cy + (y - cy) * scale_y
        return max(0, min(screen_w, cal_x)), max(0, min(screen_h, cal_y))

    def calibrate(self):
        print("[EYE] starting calibration — look at screen center")
        time.sleep(2)
        screen_w, screen_h = pyautogui.size()
        samples = []
        for _ in range(30):
            ret, frame = self._cap.read()
            if not ret:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            self._frame_timestamp += 1
            result = self._landmarker.detect_for_video(mp_img, self._frame_timestamp)
            if result.face_landmarks:
                gx, gy = self._get_gaze_point(result.face_landmarks[0], frame.shape[1], frame.shape[0])
                samples.append((gx, gy))
        if not samples:
            print("[EYE] calibration failed — no face detected")
            return False
        avg_x = float(np.mean([s[0] for s in samples]))
        avg_y = float(np.mean([s[1] for s in samples]))
        self._calibration = {
            "center_x": avg_x,
            "center_y": avg_y,
            "scale_x": 1.0,
            "scale_y": 1.0,
        }
        self._save_calibration()
        print(f"[EYE] calibrated center=({avg_x:.0f}, {avg_y:.0f})")
        return True

    def _load_calibration(self):
        try:
            if os.path.exists(CALIBRATION_FILE):
                with open(CALIBRATION_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_calibration(self):
        try:
            os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
            with open(CALIBRATION_FILE, "w") as f:
                json.dump(self._calibration, f)
        except Exception as e:
            print(f"[EYE] calibration save error: {e}")


if __name__ == "__main__":
    ctrl = EyeController(stop_event=threading.Event())
    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()
