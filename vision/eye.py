"""Face/head cursor control (MediaPipe FaceMesh + pyautogui).

Runs in its own process. The nose tip drives the cursor; opening your mouth
performs a click. This is more robust than raw gaze tracking. Press Q to quit.
"""

import time


def run() -> None:
    import cv2
    import mediapipe as mp
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0

    screen_w, screen_h = pyautogui.size()
    smooth = 0.4
    sensitivity = 2.2       # amplify small head movements
    mouth_open_ratio = 0.05
    click_cooldown = 0.8

    mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.6, min_tracking_confidence=0.6)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[VISION] camera not available", flush=True)
        return

    px, py = screen_w / 2, screen_h / 2
    last_click = 0.0
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            res = mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_face_landmarks:
                lm = res.multi_face_landmarks[0].landmark
                nose = lm[1]
                # Map nose offset from center, amplified, to the full screen.
                dx = (nose.x - 0.5) * sensitivity + 0.5
                dy = (nose.y - 0.5) * sensitivity + 0.5
                tgt_x = min(max(dx, 0), 1) * screen_w
                tgt_y = min(max(dy, 0), 1) * screen_h
                px += (tgt_x - px) * smooth
                py += (tgt_y - py) * smooth
                pyautogui.moveTo(int(px), int(py))

                upper, lower = lm[13], lm[14]
                if abs(lower.y - upper.y) > mouth_open_ratio and time.time() - last_click > click_cooldown:
                    pyautogui.click()
                    last_click = time.time()

            cv2.putText(frame, "Face control - open mouth to click, Q to quit",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 255), 2)
            cv2.imshow("Nexi Face Control", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        mesh.close()
