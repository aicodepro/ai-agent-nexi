import os


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def probe_mediapipe_gpu() -> dict:
    """Test whether the installed MediaPipe can actually use the GPU delegate."""
    result = {"mediapipe_gpu": False, "xnnpack": False, "error": None}
    try:
        from mediapipe.tasks import python
        gpu_delegate = python.BaseOptions.Delegate.GPU
        from mediapipe.tasks.python import vision
        mp = __import__("mediapipe")
        model_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "data", "mediapipe_models", "hand_landmarker.task",
        )
        if os.path.exists(model_path):
            options = vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(
                    model_asset_path=model_path, delegate=gpu_delegate
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1,
            )
            try:
                landmarker = vision.HandLandmarker.create_from_options(options)
                landmarker.close()
                result["mediapipe_gpu"] = True
            except Exception as e:
                result["error"] = str(e)
        result["xnnpack"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def detect_gpu():
    result = {
        "available": False,
        "backend": "cpu",
        "device": "cpu",
        "cuda_torch": False,
        "cuda_opencv": False,
        "mediapipe_gpu": False,
        "xnnpack": False,
        "name": "",
        "nvidia": False,
        "gpu_model": "",
    }
    if not _env_bool("CAMERA_USE_GPU", True):
        print("[CAMERA] GPU disabled by env")
        return result

    try:
        import cv2
        try:
            count = cv2.cuda.getCudaEnabledDeviceCount()
            if count > 0:
                result["cuda_opencv"] = True
                result["available"] = True
                result["backend"] = "opencv"
                result["device"] = "cuda"
                print(f"[CAMERA] OpenCV CUDA available: {count} device(s)")
        except Exception:
            pass
    except ImportError:
        pass
    except Exception as e:
        print(f"[CAMERA] OpenCV CUDA detection failed: {e}")

    try:
        import torch
        if torch.cuda.is_available():
            result["cuda_torch"] = True
            result["available"] = True
            result["nvidia"] = True
            device_name = torch.cuda.get_device_name(0)
            result["gpu_model"] = device_name
            if not result["backend"] or result["backend"] == "cpu":
                result["backend"] = "torch"
                result["device"] = device_name
                result["name"] = device_name
            print(f"[CAMERA] torch CUDA available: {device_name}")
        else:
            print("[CAMERA] torch available but no CUDA device")
            if not result["backend"]:
                result["backend"] = "torch_cpu"
    except ImportError:
        print("[CAMERA] torch not installed")
    except Exception as e:
        print(f"[CAMERA] torch detection failed: {e}")

    mp_gpu = probe_mediapipe_gpu()
    result["mediapipe_gpu"] = mp_gpu["mediapipe_gpu"]
    result["xnnpack"] = mp_gpu["xnnpack"]
    if mp_gpu["mediapipe_gpu"]:
        result["available"] = True
        if not result["backend"] or result["backend"] == "cpu":
            result["backend"] = "mediapipe_gpu"
            result["device"] = "gpu"
        print("[CAMERA] MediaPipe GPU delegate: AVAILABLE")
    else:
        if mp_gpu["xnnpack"]:
            print("[CAMERA] MediaPipe GPU delegate: UNAVAILABLE (CPU-only pip build)")
            print("[CAMERA] Using XNNPACK CPU delegate for optimized inference")

    if not result["available"]:
        print("[CAMERA] no GPU detected — using CPU")
    return result


gpu_info = detect_gpu()
gpu_available = gpu_info["available"]
gpu_backend = gpu_info["backend"]
