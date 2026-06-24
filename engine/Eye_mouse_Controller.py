import threading

from engine.camera_control.eye_controller import EyeController


def Eye_mouse_Controller():
    stop_evt = threading.Event()
    ctrl = EyeController(stop_event=stop_evt)
    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()


if __name__ == "__main__":
    Eye_mouse_Controller()
