import builtins
import importlib
import sys
import threading
import time
import types


def test_gpu_detection_is_lazy_on_module_reload(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    import engine.camera_control.gpu as gpu

    heavy_imports = []
    real_import = builtins.__import__

    def track_import(name, *args, **kwargs):
        if name == "cv2" or name == "torch" or name.startswith("mediapipe"):
            heavy_imports.append(name)
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("CAMERA_USE_GPU", "true")
    monkeypatch.setattr(builtins, "__import__", track_import)
    importlib.reload(gpu)

    assert heavy_imports == []


def test_gpu_detection_result_is_cached(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    import engine.camera_control.gpu as gpu

    calls = []
    expected = {"available": False, "backend": "cpu"}
    monkeypatch.setattr(gpu, "_gpu_info", None, raising=False)
    monkeypatch.setattr(gpu, "detect_gpu", lambda: calls.append(True) or expected)

    assert gpu.get_gpu_info() is expected
    assert gpu.get_gpu_info() is expected
    assert len(calls) == 1


def test_shared_click_cooldown_is_thread_safe(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import mouse_actions

    mouse_actions._reset_state()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def click(**_kwargs):
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            release.wait(1)

    monkeypatch.setattr(mouse_actions.time, "time", lambda: 100.0)
    monkeypatch.setattr(mouse_actions.pyautogui, "click", click)

    first = threading.Thread(target=mouse_actions.left_click)
    second = threading.Thread(target=mouse_actions.left_click)
    first.start()
    assert entered.wait(1)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(1)
    second.join(1)

    assert calls == [True]


def test_shared_drag_state_is_thread_safe(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import mouse_actions

    mouse_actions._reset_state()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def mouse_down(**_kwargs):
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            release.wait(1)

    monkeypatch.setattr(mouse_actions.pyautogui, "mouseDown", mouse_down)

    first = threading.Thread(target=mouse_actions.start_drag)
    second = threading.Thread(target=mouse_actions.start_drag)
    first.start()
    assert entered.wait(1)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(1)
    second.join(1)

    assert calls == [True]
    assert mouse_actions.is_dragging() is True
    mouse_actions._reset_state()


def test_face_camera_cache_opens_once_across_threads(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import face_recognizer

    entered = threading.Event()
    release = threading.Event()
    created = []

    class Capture:
        def isOpened(self):
            return True

        def set(self, *_args):
            pass

        def release(self):
            pass

    class Cv2:
        CAP_PROP_FRAME_WIDTH = 1
        CAP_PROP_FRAME_HEIGHT = 2

        def VideoCapture(self, _index):
            created.append(Capture())
            if len(created) == 1:
                entered.set()
                release.wait(1)
            return created[-1]

        def destroyAllWindows(self):
            pass

    face_recognizer._camera_cache = None
    face_recognizer._camera_cache_cv2 = None
    cv2 = Cv2()
    first = threading.Thread(target=face_recognizer._open_camera, args=(cv2,))
    second = threading.Thread(target=face_recognizer._open_camera, args=(cv2,))
    first.start()
    assert entered.wait(1)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(1)
    second.join(1)

    assert len(created) == 1
    face_recognizer._close_camera()


def test_gaze_calculation_handles_incomplete_landmarks(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control.eye_controller import EyeController

    class Landmark:
        x = 0.25
        y = 0.75

    controller = EyeController.__new__(EyeController)

    assert controller._get_gaze_point([Landmark()] * 10, 640, 480) == (320, 240)


def test_blink_check_ignores_incomplete_landmarks(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control.eye_controller import EyeController

    controller = EyeController.__new__(EyeController)
    controller._blink_enabled = True
    controller._last_blink_time = 0.0

    controller._check_blink([], None)


def test_dnn_detection_falls_back_when_network_is_uninitialized(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control.face_recognizer import FaceRecognizer

    recognizer = FaceRecognizer.__new__(FaceRecognizer)
    recognizer._dnn_net = None
    expected = ([(1, 2, 3, 4)], "gray")
    recognizer._detect_faces_haar = lambda _frame: expected

    assert recognizer._detect_faces_dnn(object()) == expected


def test_skipped_frames_do_not_reset_palm_dwell(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller

    stop_event = threading.Event()

    class Frame:
        shape = (240, 320, 3)

    class Capture:
        def __init__(self):
            self.reads = 0

        def set(self, *_args):
            pass

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            if self.reads == 4:
                stop_event.set()
            return True, Frame()

        def release(self):
            pass

    class Landmark:
        x = 0.5
        y = 0.5

    class Landmarker:
        def detect_for_video(self, *_args):
            return type("Result", (), {"hand_landmarks": [[Landmark()] * 21]})()

        def close(self):
            pass

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    capture = Capture()
    monkeypatch.setattr(hand_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(hand_controller.cv2, "flip", lambda frame, _axis: frame)
    monkeypatch.setattr(hand_controller.cv2, "cvtColor", lambda frame, _mode: frame)
    monkeypatch.setattr(hand_controller.cv2, "resize", lambda frame, _size: frame)
    monkeypatch.setattr(hand_controller.cv2, "imshow", lambda *_args: None)
    monkeypatch.setattr(hand_controller.cv2, "waitKey", lambda _delay: -1)
    monkeypatch.setattr(hand_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(hand_controller.mp, "Image", lambda **_kwargs: object())
    monkeypatch.setattr(hand_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(hand_controller.vision, "HandLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        hand_controller.vision.HandLandmarker,
        "create_from_options",
        lambda _options: Landmarker(),
    )
    monkeypatch.setattr(hand_controller.pyautogui, "size", lambda: (1920, 1080))

    controller = hand_controller.HandController(stop_event=stop_event)
    controller._frame_skip = 2
    processed = []
    controller._process_gesture = lambda _frame, landmarks, _w, _h: processed.append(landmarks)

    controller.run()

    assert [len(landmarks) for landmarks in processed] == [21, 21]


def test_palm_dwell_persists_until_threshold_and_resets_when_cleared(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller

    controller = hand_controller.HandController(stop_event=threading.Event())
    controller._is_open_palm = lambda _landmarks: 1.0
    controller._is_scroll = lambda _landmarks: (False, 0.0)
    controller._is_pinch = lambda _landmarks: False
    controller._is_middle_pinch = lambda _landmarks: False
    monkeypatch.setattr(hand_controller, "move_cursor", lambda *_args: None)
    screenshots = []
    monkeypatch.setattr(hand_controller, "screenshot", lambda: screenshots.append(True))
    times = iter([100.0, 100.5, 101.1, 101.2, 102.0])
    monkeypatch.setattr(hand_controller.time, "time", lambda: next(times))
    landmarks = [(0.5, 0.5)] * 21

    controller._process_gesture(None, landmarks, 1920, 1080)
    controller._process_gesture(None, landmarks, 1920, 1080)
    controller._process_gesture(None, landmarks, 1920, 1080)
    controller._process_gesture(None, landmarks, 1920, 1080)

    assert controller._gesture_state["palm_start"] == 100.0
    assert screenshots == [True]

    controller._is_open_palm = lambda _landmarks: 0.0
    controller._process_gesture(None, landmarks, 1920, 1080)

    assert controller._gesture_state["palm_start"] is None


def test_hand_model_load_failure_returns_unavailable(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller

    stop_event = threading.Event()

    class Capture:
        released = False

        def set(self, *_args):
            pass

        def release(self):
            self.released = True

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    capture = Capture()
    monkeypatch.setattr(hand_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(hand_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(hand_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(hand_controller.vision, "HandLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        hand_controller.vision.HandLandmarker,
        "create_from_options",
        lambda _options: (_ for _ in ()).throw(RuntimeError("bad model")),
    )

    result = hand_controller.HandController(stop_event=stop_event).run()

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_load_failed"
    assert stop_event.is_set()
    assert capture.released is True


def test_eye_model_load_failure_returns_unavailable(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import eye_controller

    stop_event = threading.Event()

    class Capture:
        released = False

        def set(self, *_args):
            pass

        def release(self):
            self.released = True

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    capture = Capture()
    monkeypatch.setattr(eye_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(eye_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(eye_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(eye_controller.vision, "FaceLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        eye_controller.vision.FaceLandmarker,
        "create_from_options",
        lambda _options: (_ for _ in ()).throw(RuntimeError("bad model")),
    )

    result = eye_controller.EyeController(stop_event=stop_event).run()

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["reason"] == "model_load_failed"
    assert stop_event.is_set()
    assert capture.released is True


def test_hand_camera_disconnect_backs_off_then_reports_unavailable(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller

    class StopEvent:
        def __init__(self):
            self.stopped = False
            self.waits = []

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, timeout):
            self.waits.append(timeout)
            return False

    class Capture:
        def __init__(self):
            self.reads = 0

        def set(self, *_args):
            pass

        def isOpened(self):
            return self.reads < 5

        def read(self):
            self.reads += 1
            return False, None

        def release(self):
            pass

    class Landmarker:
        def close(self):
            pass

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    stop_event = StopEvent()
    capture = Capture()
    monkeypatch.setattr(hand_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(hand_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(hand_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(hand_controller.vision, "HandLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        hand_controller.vision.HandLandmarker,
        "create_from_options",
        lambda _options: Landmarker(),
    )
    monkeypatch.setattr(hand_controller.pyautogui, "size", lambda: (1920, 1080))

    result = hand_controller.HandController(stop_event=stop_event).run()

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["reason"] == "camera_disconnected"
    assert capture.reads == 3
    assert stop_event.waits


def test_eye_camera_disconnect_backs_off_then_reports_unavailable(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import eye_controller

    class StopEvent:
        def __init__(self):
            self.stopped = False
            self.waits = []

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, timeout):
            self.waits.append(timeout)
            return False

    class Capture:
        def __init__(self):
            self.reads = 0

        def set(self, *_args):
            pass

        def isOpened(self):
            return self.reads < 5

        def read(self):
            self.reads += 1
            return False, None

        def release(self):
            pass

    class Landmarker:
        def close(self):
            pass

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    stop_event = StopEvent()
    capture = Capture()
    monkeypatch.setattr(eye_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(eye_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(eye_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(eye_controller.vision, "FaceLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        eye_controller.vision.FaceLandmarker,
        "create_from_options",
        lambda _options: Landmarker(),
    )
    monkeypatch.setattr(eye_controller.pyautogui, "size", lambda: (1920, 1080))

    result = eye_controller.EyeController(stop_event=stop_event).run()

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["reason"] == "camera_disconnected"
    assert capture.reads == 3
    assert stop_event.waits


def test_face_camera_disconnect_backs_off_then_reports_unavailable(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import face_recognizer

    class StopEvent:
        def __init__(self):
            self.stopped = False
            self.waits = []
            self.capture = None

        def is_set(self):
            return self.stopped or (self.capture is not None and self.capture.reads >= 5)

        def set(self):
            self.stopped = True

        def wait(self, timeout):
            self.waits.append(timeout)
            return False

    class Capture:
        def __init__(self):
            self.reads = 0

        def set(self, *_args):
            pass

        def isOpened(self):
            return self.reads < 5

        def read(self):
            self.reads += 1
            return False, None

        def release(self):
            pass

    class Recognizer:
        def read(self, _path):
            pass

    capture = Capture()
    cv2 = types.ModuleType("cv2")
    cv2.CAP_PROP_FRAME_WIDTH = 1
    cv2.CAP_PROP_FRAME_HEIGHT = 2
    cv2.VideoCapture = lambda _index: capture
    cv2.destroyAllWindows = lambda: None
    cv2.face = type("Face", (), {"LBPHFaceRecognizer_create": staticmethod(Recognizer)})()
    fr = types.ModuleType("FaceRecognition")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "FaceRecognition", fr)
    monkeypatch.setattr(face_recognizer.os.path, "exists", lambda _path: False)
    face_recognizer._camera_cache = None
    face_recognizer._camera_cache_cv2 = None
    stop_event = StopEvent()
    stop_event.capture = capture

    result = face_recognizer.FaceRecognizer(stop_event=stop_event, model_path="missing").run()

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["reason"] == "camera_disconnected"
    assert capture.reads == 3
    assert stop_event.waits


def test_face_registration_disconnect_backs_off_then_stops(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import face_recognizer

    class Capture:
        def __init__(self):
            self.reads = 0

        def set(self, *_args):
            pass

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            return False, None

        def release(self):
            pass

    capture = Capture()
    cv2 = types.ModuleType("cv2")
    cv2.CAP_PROP_FRAME_WIDTH = 1
    cv2.CAP_PROP_FRAME_HEIGHT = 2
    cv2.VideoCapture = lambda _index: capture
    cv2.destroyAllWindows = lambda: None
    fr = types.ModuleType("FaceRecognition")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "FaceRecognition", fr)
    times = iter([0.0, 0.0, 0.0, 0.0, 0.0, 11.0])
    waits = []
    monkeypatch.setattr(face_recognizer.time, "time", lambda: next(times))
    monkeypatch.setattr(face_recognizer.time, "sleep", waits.append)
    face_recognizer._camera_cache = None
    face_recognizer._camera_cache_cv2 = None

    result = face_recognizer.register_new_face(duration_s=10)

    assert result is False
    assert capture.reads == 3
    assert waits
    face_recognizer._close_camera()


def test_hand_controller_catches_failsafe_and_stops(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller

    stop_event = threading.Event()

    class Frame:
        shape = (240, 320, 3)

    class Capture:
        released = False

        def set(self, *_args):
            pass

        def isOpened(self):
            return True

        def read(self):
            stop_event.set()
            return True, Frame()

        def release(self):
            self.released = True

    class Landmarker:
        def detect_for_video(self, *_args):
            return type("Result", (), {"hand_landmarks": []})()

        def close(self):
            pass

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    capture = Capture()
    monkeypatch.setattr(hand_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(hand_controller.cv2, "flip", lambda frame, _axis: frame)
    monkeypatch.setattr(hand_controller.cv2, "cvtColor", lambda frame, _mode: frame)
    monkeypatch.setattr(hand_controller.cv2, "resize", lambda frame, _size: frame)
    monkeypatch.setattr(hand_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(hand_controller.mp, "Image", lambda **_kwargs: object())
    monkeypatch.setattr(hand_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(hand_controller.vision, "HandLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        hand_controller.vision.HandLandmarker,
        "create_from_options",
        lambda _options: Landmarker(),
    )
    monkeypatch.setattr(hand_controller.pyautogui, "size", lambda: (1920, 1080))
    controller = hand_controller.HandController(stop_event=stop_event)
    controller._frame_skip = 1
    controller._process_gesture = lambda *_args: (_ for _ in ()).throw(
        hand_controller.pyautogui.FailSafeException("corner")
    )

    result = controller.run()

    assert result["ok"] is False
    assert result["status"] == "stopped"
    assert result["reason"] == "failsafe"
    assert capture.released is True


def test_eye_controller_catches_failsafe_and_stops(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import eye_controller

    stop_event = threading.Event()

    class Frame:
        shape = (480, 640, 3)

    class Capture:
        released = False

        def set(self, *_args):
            pass

        def isOpened(self):
            return True

        def read(self):
            stop_event.set()
            return True, Frame()

        def release(self):
            self.released = True

    class Landmarker:
        def detect_for_video(self, *_args):
            return type("Result", (), {"face_landmarks": [[object()] * 198]})()

        def close(self):
            pass

    class BaseOptions:
        class Delegate:
            CPU = "cpu"
            GPU = "gpu"

        def __init__(self, **_kwargs):
            pass

    capture = Capture()
    monkeypatch.setattr(eye_controller.cv2, "VideoCapture", lambda _index: capture)
    monkeypatch.setattr(eye_controller.cv2, "flip", lambda frame, _axis: frame)
    monkeypatch.setattr(eye_controller.cv2, "cvtColor", lambda frame, _mode: frame)
    monkeypatch.setattr(eye_controller.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(eye_controller.mp, "Image", lambda **_kwargs: object())
    monkeypatch.setattr(eye_controller.python, "BaseOptions", BaseOptions)
    monkeypatch.setattr(eye_controller.vision, "FaceLandmarkerOptions", lambda **_kwargs: object())
    monkeypatch.setattr(
        eye_controller.vision.FaceLandmarker,
        "create_from_options",
        lambda _options: Landmarker(),
    )
    monkeypatch.setattr(eye_controller.pyautogui, "size", lambda: (1920, 1080))
    monkeypatch.setattr(
        eye_controller,
        "move_cursor",
        lambda *_args: (_ for _ in ()).throw(eye_controller.pyautogui.FailSafeException("corner")),
    )
    controller = eye_controller.EyeController(stop_event=stop_event)
    controller._get_gaze_point = lambda *_args: (320, 240)

    result = controller.run()

    assert result["ok"] is False
    assert result["status"] == "stopped"
    assert result["reason"] == "failsafe"
    assert capture.released is True


def test_hand_failsafe_during_drag_cleanup_clears_state(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    from engine.camera_control import hand_controller, mouse_actions

    mouse_actions._reset_state()
    mouse_actions._drag_active = True
    monkeypatch.setattr(
        mouse_actions.pyautogui,
        "mouseUp",
        lambda **_kwargs: (_ for _ in ()).throw(mouse_actions.pyautogui.FailSafeException("corner")),
    )
    monkeypatch.setattr(hand_controller.cv2, "destroyAllWindows", lambda: None)
    controller = hand_controller.HandController.__new__(hand_controller.HandController)
    controller._landmarker = None
    controller._cap = None

    controller._stop()

    assert mouse_actions.is_dragging() is False


def test_camera_thread_failure_updates_structured_status(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    import engine.camera_control as camera

    gpu = {
        "available": False,
        "backend": "cpu",
        "device": "cpu",
        "mediapipe_gpu": False,
        "xnnpack": False,
        "nvidia": False,
        "gpu_model": "",
        "cuda_torch": False,
        "cuda_opencv": False,
    }

    class Controller:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            return {"ok": False, "status": "unavailable", "reason": "model_load_failed"}

    class ImmediateThread:
        def __init__(self, target, args=(), **_kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

        def is_alive(self):
            return False

    camera._running = False
    monkeypatch.setattr(camera, "get_gpu_info", lambda: gpu)
    monkeypatch.setattr(camera, "HandController", Controller)
    monkeypatch.setattr(camera.threading, "Thread", ImmediateThread)

    assert camera.start_camera_control("hand") is True
    status = camera.get_status()

    assert status["running"] is False
    assert status["status"] == "unavailable"
    assert status["reason"] == "model_load_failed"


def test_camera_controller_boundary_cleans_up_failsafe(monkeypatch):
    monkeypatch.setenv("CAMERA_USE_GPU", "false")
    monkeypatch.setenv("CAMERA_ON_STARTUP", "false")
    monkeypatch.setenv("FACE_RECOGNITION_ON_STARTUP", "false")
    import engine.camera_control as camera
    from engine.camera_control.mouse_actions import pyautogui

    class Controller:
        stopped = False

        def run(self):
            raise pyautogui.FailSafeException("corner")

        def stop(self):
            self.stopped = True

    controller = Controller()
    camera._running = True
    camera._stop_event.clear()

    camera._run_camera_controller(controller)

    assert controller.stopped is True
    assert camera._stop_event.is_set()
    assert camera._last_status["status"] == "stopped"
    assert camera._last_status["reason"] == "failsafe"
