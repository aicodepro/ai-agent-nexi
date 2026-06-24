"""Nexi — Desktop AI Assistant launcher.

Dual-process architecture:
  Process 1: UI + Command Engine (Eel web server)
  Process 2: Audio Wake Pipeline (mic → hotword/clap → ASR → bridge)
"""

import multiprocessing
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def start_ui(command_queue=None, stop_event=None, wake_ready=None, speaking_event=None):
    """Process 1: UI + command engine."""
    print(f"[NEXI] ui_process pid={os.getpid()}", flush=True)
    from main import main
    main(command_queue=command_queue, stop_event=stop_event, wake_ready=wake_ready,
         speaking_event=speaking_event)


def start_wake(command_queue=None, stop_event=None, wake_ready=None, speaking_event=None):
    """Process 2: Audio wake pipeline."""
    print(f"[NEXI] wake_process pid={os.getpid()}", flush=True)
    try:
        from wake.pipeline import start_pipeline, is_running
        start_pipeline(command_queue=command_queue, speaking_event=speaking_event)
        if is_running():
            print("[NEXI] wake pipeline running", flush=True)
            # Signal the UI that wake detection is up before it opens the window.
            if wake_ready is not None:
                wake_ready.set()
            while True:
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1.0)
            return
        print("[NEXI] wake pipeline failed to start", flush=True)
    except Exception as e:
        print(f"[NEXI] wake_failed reason={type(e).__name__}: {e}", flush=True)

    # Even on failure, release the UI so it doesn't wait forever.
    if wake_ready is not None:
        wake_ready.set()

    # Block until stop
    while stop_event and not stop_event.is_set():
        time.sleep(1.0)


if __name__ == "__main__":
    command_queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()
    wake_ready = multiprocessing.Event()
    speaking_event = multiprocessing.Event()
    print(f"[NEXI] starting pid={os.getpid()}", flush=True)

    p1 = multiprocessing.Process(target=start_ui, args=(command_queue, stop_event, wake_ready, speaking_event))
    p2 = multiprocessing.Process(target=start_wake, args=(command_queue, stop_event, wake_ready, speaking_event))

    try:
        # Start the wake process first so its pipeline can come up while the
        # UI process waits for the wake_ready signal before showing the window.
        p2.start()
        print(f"[NEXI] wake_process spawned pid={p2.pid}", flush=True)
        p1.start()
        print(f"[NEXI] ui_process spawned pid={p1.pid}", flush=True)

        p1.join()
    except KeyboardInterrupt:
        print("[NEXI] shutdown requested", flush=True)
    finally:
        stop_event.set()
        if p2.is_alive():
            p2.terminate()
            p2.join(timeout=3)
        print("[NEXI] stopped", flush=True)
