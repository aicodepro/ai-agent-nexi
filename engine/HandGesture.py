import threading

from engine.camera_control.hand_controller import HandController


def HandGesture():
    stop_evt = threading.Event()
    ctrl = HandController(stop_event=stop_evt)
    try:
        ctrl.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()


if __name__ == "__main__":
    HandGesture()
