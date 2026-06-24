from __future__ import annotations

import cv2


def main() -> int:
    found = False
    for index in range(4):
        cap = cv2.VideoCapture(index)
        ok = cap.isOpened()
        print(f"[CAMERA] device index={index} available={str(ok).lower()}")
        if ok:
            found = True
        cap.release()
    if not found:
        print("[CAMERA] no_camera_found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
