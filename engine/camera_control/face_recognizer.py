import threading
import time
import os

MODEL_PATH_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "trainingData.yml"
)
_MODEL_FALLBACK = os.path.join("E:", os.sep, "jarvis-main", "trainingData.yml")

_DNN_FACE_PROTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "deploy.proto.txt"
)
_DNN_FACE_MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "res10_300x300_ssd_iter_140000_fp16.caffemodel"
)
CAMERA_READ_FAILURE_LIMIT = 3
CAMERA_READ_FAILURE_BACKOFF = 0.1


# ── Lazy camera cache ────────────────────────────────────────────────────────
# Prevents opening the camera multiple times within the same process.
_camera_cache = None
_camera_cache_cv2 = None
_camera_cache_lock = threading.RLock()


def _open_camera(cv2_module):
    """Open camera lazily and cache the handle — never open twice in one process.

    Returns the cached cv2.VideoCapture handle (already set to 640x480).
    Callers should *not* release the handle; use _close_camera() at shutdown.
    """
    global _camera_cache, _camera_cache_cv2
    with _camera_cache_lock:
        if _camera_cache is not None and _camera_cache.isOpened():
            return _camera_cache
        _camera_cache = cv2_module.VideoCapture(0)
        if _camera_cache.isOpened():
            _camera_cache.set(cv2_module.CAP_PROP_FRAME_WIDTH, 640)
            _camera_cache.set(cv2_module.CAP_PROP_FRAME_HEIGHT, 480)
            print("[CAMERA] lazy_init at 640x480", flush=True)
        else:
            print("[CAMERA] lazy_init_failed", flush=True)
        _camera_cache_cv2 = cv2_module
        return _camera_cache


def _close_camera():
    """Release the cached camera handle (call at process shutdown)."""
    global _camera_cache, _camera_cache_cv2
    with _camera_cache_lock:
        if _camera_cache is not None:
            try:
                _camera_cache.release()
                print("[CAMERA] cache_released", flush=True)
            except Exception:
                pass
            _camera_cache = None
        if _camera_cache_cv2 is not None:
            try:
                _camera_cache_cv2.destroyAllWindows()
            except Exception:
                pass
            _camera_cache_cv2 = None


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


class FaceRecognizer:
    def __init__(self, stop_event: threading.Event, model_path: str = "",
                 names: dict | None = None, auth_gate: bool = False):
        self._stop_event = stop_event
        self._model_path = model_path or MODEL_PATH_DEFAULT
        self._names = names or {0: "User"}
        self._auth_gate = auth_gate
        self._cap = None
        self._face_recognizer = None
        self._cv2 = None
        self._fr = None
        self._dnn_net = None
        self._authenticated = False
        self._last_seen_name = ""
        self._detect_count = 0
        self._auth_min_detections = int(os.getenv("FACE_RECOGNITION_AUTH_MIN_DETECTIONS", "5"))

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_seen_name(self) -> str:
        return self._last_seen_name

    def _init_dnn(self):
        if not os.path.exists(_DNN_FACE_PROTO) or not os.path.exists(_DNN_FACE_MODEL):
            return None
        try:
            net = self._cv2.dnn.readNetFromCaffe(_DNN_FACE_PROTO, _DNN_FACE_MODEL)
            try:
                net.setPreferableBackend(self._cv2.dnn.DNN_BACKEND_CUDA)
                net.setPreferableTarget(self._cv2.dnn.DNN_TARGET_CUDA)
                print("[FACE] dnn_gpu_enabled backend=CUDA")
            except Exception:
                print("[FACE] dnn_gpu_unavailable falling_back_to=cpu")
            return net
        except Exception as e:
            print(f"[FACE] dnn_load_error reason={type(e).__name__}")
            return None

    def _detect_faces_dnn(self, frame):
        if self._dnn_net is None:
            return self._detect_faces_haar(frame)
        import numpy as np
        h, w = frame.shape[:2]
        blob = self._cv2.dnn.blobFromImage(
            self._cv2.resize(frame, (300, 300)), 1.0,
            (300, 300), (104.0, 177.0, 123.0)
        )
        self._dnn_net.setInput(blob)
        detections = self._dnn_net.forward()
        faces = []
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
        for i in range(detections.shape[2]):
            conf = detections[0, 0, i, 2]
            if conf > 0.7:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (x1, y1, x2, y2) = box.astype("int")
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w - 1, x2), min(h - 1, y2)
                faces.append((x1, y1, x2 - x1, y2 - y1))
        return faces, gray

    def _detect_faces_haar(self, frame):
        return self._fr.faceDetection(frame)

    def _detect_faces(self, frame):
        if self._dnn_net is not None:
            return self._detect_faces_dnn(frame)
        return self._detect_faces_haar(frame)

    def run(self):
        try:
            import cv2
            import FaceRecognition as fr
            self._cv2 = cv2
            self._fr = fr
        except ImportError as e:
            print(f"[FACE] import_error reason={type(e).__name__} — FaceRecognition or cv2 not available")
            return

        self._dnn_net = self._init_dnn()

        model_path = None
        try:
            self._face_recognizer = self._cv2.face.LBPHFaceRecognizer_create()
            candidates = [
                self._model_path,
                os.path.join(os.path.dirname(__file__), "..", "..", "trainingData.yml"),
                _MODEL_FALLBACK,
            ]
            for c in candidates:
                if c and os.path.exists(c):
                    model_path = c
                    break
            if model_path is None:
                print(f"[FACE] model_not_found — no training data, auth will use detection-only", flush=True)
            else:
                self._face_recognizer.read(model_path)
                print(f"[FACE] model_loaded path={model_path}", flush=True)
        except Exception as e:
            print(f"[FACE] model_load_error reason={type(e).__name__}, auth will use detection-only", flush=True)
            model_path = None

        self._cap = _open_camera(self._cv2)
        if not self._cap.isOpened():
            print("[FACE] camera_open_failed")
            return

        confidence_threshold = int(os.getenv("FACE_RECOGNITION_CONFIDENCE_THRESHOLD", "80"))
        model_loaded = model_path is not None and os.path.exists(model_path) if model_path else False
        read_failures = 0

        try:
            while not self._stop_event.is_set():
                ret, frame = self._cap.read()
                if not ret:
                    read_failures += 1
                    if read_failures >= CAMERA_READ_FAILURE_LIMIT:
                        self._stop_event.set()
                        print("[FACE] camera_disconnected", flush=True)
                        return {
                            "ok": False,
                            "status": "unavailable",
                            "reason": "camera_disconnected",
                        }
                    self._stop_event.wait(CAMERA_READ_FAILURE_BACKOFF)
                    continue
                read_failures = 0

                faces_detected, gray_img = self._detect_faces(frame)

                for (x, y, w, h) in faces_detected:
                    self._cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 6)

                for face in faces_detected:
                    (x, y, w, h) = face
                    roi_gray = gray_img[y:y + w, x:x + h]
                    if roi_gray.size == 0:
                        continue
                    predicted_name = "Unknown"
                    confidence = 999
                    if model_loaded:
                        try:
                            label, confidence = self._face_recognizer.predict(roi_gray)
                            predicted_name = self._names.get(label, "Unknown")
                        except Exception:
                            continue
                    self._last_seen_name = predicted_name
                    det = self._detect_count

                    if model_loaded and confidence < confidence_threshold:
                        self._authenticated = True
                        self._detect_count += 1
                        self._fr.put_text(frame,
                            f"{predicted_name} ({confidence:.0f})", x, y)
                        print(f"[FACE] match name={predicted_name} confidence={confidence:.0f} count={self._detect_count}", flush=True)
                    elif model_loaded and confidence >= confidence_threshold:
                        print(f"[FACE] nomatch name={predicted_name} confidence={confidence:.0f} threshold={confidence_threshold}", flush=True)
                        self._fr.put_text(frame,
                            f"Unknown ({confidence:.0f})", x, y)
                    else:
                        self._detect_count += 1
                        self._fr.put_text(frame, predicted_name, x, y)
                        if self._detect_count >= self._auth_min_detections and not self._authenticated:
                            self._authenticated = True
                            print(f"[FACE] auth_by_detection count={self._detect_count}", flush=True)

                    self._fr.draw_rect(frame, face)

                if faces_detected:
                    label = "AUTHENTICATED" if self._authenticated else (
                        f"detecting... ({self._detect_count}/{self._auth_min_detections})"
                    )
                    self._cv2.putText(frame, label, (10, 30),
                        self._cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0) if self._authenticated else (0, 255, 255), 2)

                self._cv2.imshow("Face Recognition", frame)
                if self._cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            self._stop()

    def stop(self):
        self._stop_event.set()
        self._stop()

    def _stop(self):
        self._cap = None
        _close_camera()


def register_new_face(name: str = "User", duration_s: int = 10) -> bool:
    try:
        import cv2
        import FaceRecognition as fr
        import os
    except ImportError:
        print("[FACE] register import_error")
        return False

    cap = _open_camera(cv2)
    if not cap.isOpened():
        print("[FACE] register camera_open_failed")
        return False

    import numpy as np
    faces_data = []
    start = time.time()
    read_failures = 0
    print(f"[FACE] registering '{name}' — look at the camera for {duration_s}s")

    while time.time() - start < duration_s:
        ret, frame = cap.read()
        if not ret:
            read_failures += 1
            if read_failures >= CAMERA_READ_FAILURE_LIMIT:
                print("[FACE] register camera_disconnected", flush=True)
                _close_camera()
                return False
            time.sleep(CAMERA_READ_FAILURE_BACKOFF)
            continue
        read_failures = 0
        faces_detected, gray_img = fr.faceDetection(frame)
        for face in faces_detected:
            (x, y, w, h) = face
            roi = gray_img[y:y + h, x:x + w]
            if roi.size > 0:
                faces_data.append(roi)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.imshow("Register Face", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Don't release — _open_camera manages the shared handle
    # _close_camera() on shutdown handles cleanup

    if len(faces_data) < 5:
        print(f"[FACE] register failed — only {len(faces_data)} samples")
        return False

    label = int(os.getenv("FACE_RECOGNITION_NEW_LABEL", "0"))
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    labels = [label] * len(faces_data)
    recognizer.train(faces_data, np.array(labels))
    model_path = os.getenv("FACE_RECOGNITION_MODEL", "trainingData.yml")
    recognizer.write(model_path)
    print(f"[FACE] registered '{name}' with label={label} samples={len(faces_data)}")
    return True


if __name__ == "__main__":
    rec = FaceRecognizer(stop_event=threading.Event())
    try:
        rec.run()
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
