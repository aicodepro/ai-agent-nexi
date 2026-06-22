"""Hand-tracking mouse control (MediaPipe Hands + pyautogui).

Runs in its own process (see vision/runner.py). Index fingertip moves the
cursor; pinching thumb + index together performs a click. Press Q in the
camera window to quit.
"""

import time


def run() -> None:
    import cv2
    import mediapipe as mp
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0

    screen_w, screen_h = pyautogui.size()
    smooth = 0.35           # cursor smoothing factor (0..1)
    pinch_threshold = 0.05  # normalized distance for a "pinch"
    click_cooldown = 0.6

    hands = mp.solutions.hands.Hands(
        max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6)
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
            res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                ix, iy = lm[8].x, lm[8].y    # index fingertip
                tx, ty = lm[4].x, lm[4].y    # thumb tip
                tgt_x, tgt_y = ix * screen_w, iy * screen_h
                px += (tgt_x - px) * smooth
                py += (tgt_y - py) * smooth
                pyautogui.moveTo(int(px), int(py))

                dist = ((ix - tx) ** 2 + (iy - ty) ** 2) ** 0.5
                if dist < pinch_threshold and time.time() - last_click > click_cooldown:
                    pyautogui.click()
                    last_click = time.time()

                mp.solutions.drawing_utils.draw_landmarks(
                    frame, res.multi_hand_landmarks[0], mp.solutions.hands.HAND_CONNECTIONS)

            cv2.putText(frame, "Hand control - pinch to click, Q to quit",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 255), 2)
            cv2.imshow("Nexi Hand Control", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        hands.close()
