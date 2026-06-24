import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import pyautogui
from collections import deque

from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_utils, drawing_styles

from engine.camera_control.mouse_actions import (
    move_cursor, left_click, right_click, double_click,
    start_drag, stop_drag, is_dragging, scroll, screenshot, set_debug,
)
from engine.camera_control.smoothing import SmoothingFilter

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "mediapipe_models", "hand_landmarker.task")

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

SCROLL_GESTURE_MAX_DISTANCE = 0.10
SCROLL_DEADZONE = 0.008
SCROLL_SPEED = 800
SCROLL_MAX_STEP = 60
CLICK_COOLDOWN = 0.3
DOUBLE_CLICK_WINDOW = 0.35
PINCH_THRESHOLD = 0.03
RIGHT_CLICK_THRESHOLD = 0.035
SCREENSHOT_HOLD_SECONDS = 1.0
CURSOR_SMOOTHING_FACTOR = 0.5
CURSOR_DEADZONE = 3.0

GESTURE_IDLE = "idle"
GESTURE_POINTING = "pointing"
GESTURE_CLICK_ARMED = "click_armed"
GESTURE_DRAGGING = "dragging"
GESTURE_SCROLLING = "scrolling"
GESTURE_PAUSED = "paused"
GESTURE_SCREENSHOT = "screenshot"

DEBUG_OVERLAY = False


class HandController:
    def __init__(self, stop_event: threading.Event, use_gpu: bool = False, hybrid_eye: bool = False):
        self._stop_event = stop_event
        self._use_gpu = use_gpu
        self._hybrid_eye = hybrid_eye
        self._cap = None
        self._landmarker = None
        sf = float(os.getenv("CAMERA_CURSOR_SMOOTHING", str(CURSOR_SMOOTHING_FACTOR)))
        dz = float(os.getenv("CAMERA_CURSOR_DEADZONE", str(CURSOR_DEADZONE)))
        self._cursor_smoother = SmoothingFilter(factor=sf, deadzone=dz)
        self._state = GESTURE_IDLE
        self._last_click_time = 0.0
        self._gesture_state = {"scroll_y": None, "last_click_time": 0, "palm_start": None}
        self._click_buffer = deque(maxlen=3)
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

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH, delegate=delegate),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.65,
            min_tracking_confidence=0.65,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        screen_w, screen_h = pyautogui.size()

        try:
            while self._cap.isOpened() and not self._stop_event.is_set():
                ret, frame = self._cap.read()
                if not ret:
                    continue

                self._frame_timestamp += 1
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = self._landmarker.detect_for_video(mp_img, self._frame_timestamp)

                landmark_list = []
                if result.hand_landmarks:
                    hand_landmarks = result.hand_landmarks[0]
                    if DEBUG_OVERLAY:
                        drawing_utils.draw_landmarks(
                            frame, hand_landmarks,
                            drawing_styles.get_default_hand_connections_style(),
                        )
                    for lm in hand_landmarks:
                        landmark_list.append((lm.x, lm.y))

                self._process_gesture(frame, landmark_list, screen_w, screen_h)

                cv2.imshow("Camera Control", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == 27:
                    break
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
        if is_dragging():
            stop_drag()

    @staticmethod
    def _get_distance(a, b):
        return np.hypot(b[0] - a[0], b[1] - a[1])

    def _is_pinch(self, landmark_list) -> bool:
        if len(landmark_list) < 21:
            return False
        return self._get_distance(landmark_list[4], landmark_list[8]) < PINCH_THRESHOLD

    def _is_middle_pinch(self, landmark_list) -> bool:
        if len(landmark_list) < 21:
            return False
        return self._get_distance(landmark_list[4], landmark_list[12]) < RIGHT_CLICK_THRESHOLD

    def _is_scroll(self, landmark_list) -> tuple[bool, float]:
        if len(landmark_list) < 21:
            return False, 0.0
        idx_mid = self._get_distance(landmark_list[8], landmark_list[12])
        idx_thumb = self._get_distance(landmark_list[4], landmark_list[8])
        idx_up = landmark_list[8][1] < landmark_list[6][1]
        mid_up = landmark_list[12][1] < landmark_list[10][1]
        return idx_up and mid_up and idx_mid < SCROLL_GESTURE_MAX_DISTANCE and idx_thumb > 0.05, idx_mid

    def _is_open_palm(self, landmark_list) -> float:
        if len(landmark_list) < 21:
            return 0.0
        tip_ids = [4, 8, 12, 16, 20]
        pip_ids = [2, 6, 10, 14, 18]
        extended = 0
        for tip, pip in zip(tip_ids, pip_ids):
            if landmark_list[tip][1] < landmark_list[pip][1]:
                extended += 1
        return extended / 5.0

    def _process_gesture(self, frame, landmark_list, screen_w, screen_h):
        if not landmark_list or len(landmark_list) < 21:
            self._gesture_state["palm_start"] = None
            return

        index_tip = landmark_list[8]
        cursor_x = int(index_tip[0] * screen_w)
        cursor_y = int(index_tip[1] * screen_h)
        smooth_x, smooth_y = self._cursor_smoother.update(cursor_x, cursor_y)
        move_cursor(smooth_x, smooth_y)

        palm_ratio = self._is_open_palm(landmark_list)
        is_scrolling, _ = self._is_scroll(landmark_list)
        is_pinching = self._is_pinch(landmark_list)
        is_mid_pinching = self._is_middle_pinch(landmark_list)
        now = time.time()

        if palm_ratio >= 0.8:
            if self._gesture_state["palm_start"] is None:
                self._gesture_state["palm_start"] = now
                self._state = GESTURE_PAUSED
                print("[HAND] gesture paused (open palm)")
            return
        else:
            if self._state == GESTURE_PAUSED:
                self._state = GESTURE_IDLE
                print("[HAND] gesture resumed")
            self._gesture_state["palm_start"] = None

        if is_scrolling:
            self._state = GESTURE_SCROLLING
            mid_y = (landmark_list[8][1] + landmark_list[12][1]) / 2.0
            prev = self._gesture_state.get("scroll_y")
            self._gesture_state["scroll_y"] = mid_y
            if prev is not None:
                delta = prev - mid_y
                if abs(delta) > SCROLL_DEADZONE:
                    step = int(np.clip(delta * SCROLL_SPEED, -SCROLL_MAX_STEP, SCROLL_MAX_STEP))
                    if step != 0:
                        scroll(step)
            return
        else:
            self._gesture_state["scroll_y"] = None

        if is_pinching:
            if self._state == GESTURE_DRAGGING:
                return

            if now - self._last_click_time > CLICK_COOLDOWN:
                self._click_buffer.append(now)

                if len(self._click_buffer) >= 2:
                    gap = self._click_buffer[-1] - self._click_buffer[-2]
                    if gap < DOUBLE_CLICK_WINDOW:
                        double_click()
                        self._click_buffer.clear()
                        self._last_click_time = now
                        self._state = GESTURE_CLICK_ARMED
                        return

                if len(self._click_buffer) >= 4:
                    self._click_buffer.clear()
                    start_drag()
                    self._state = GESTURE_DRAGGING
                    return

                left_click()
                self._last_click_time = now
                self._state = GESTURE_CLICK_ARMED
            return

        if is_mid_pinching and not is_pinching:
            if now - self._last_click_time > CLICK_COOLDOWN:
                right_click()
                self._last_click_time = now
            return

        if self._state == GESTURE_DRAGGING:
            stop_drag()
            self._state = GESTURE_IDLE

        if self._state in (GESTURE_CLICK_ARMED,):
            self._state = GESTURE_IDLE

        if self._state == GESTURE_IDLE:
            pass


if __name__ == "__main__":
    ctrl = HandController(stop_event=threading.Event())
    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()