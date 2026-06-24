import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import time
from collections import deque

# Function to calculate Euclidean distance between two points
def get_distance(a, b):
    return np.hypot(b[0] - a[0], b[1] - a[1])

# Screen dimensions
screen_width, screen_height = pyautogui.size()

# MediaPipe Hands initialization
mpHands = mp.solutions.hands
hands = mpHands.Hands(
    static_image_mode=False,
    model_complexity=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
    max_num_hands=1
)

draw = mp.solutions.drawing_utils

# Buffer size for temporal consistency
BUFFER_SIZE = 5

# Buffers for storing distances for smoothing and consistency
scroll_buffer = deque(maxlen=BUFFER_SIZE)
click_buffer = deque(maxlen=BUFFER_SIZE)
zoom_buffer = deque(maxlen=BUFFER_SIZE)
tab_switch_buffer = deque(maxlen=BUFFER_SIZE)

# Function to find finger tips
def find_finger_tips(processed):
    if processed.multi_hand_landmarks:
        hand_landmarks = processed.multi_hand_landmarks[0]  # Assuming only one hand is detected
        index_finger_tip = hand_landmarks.landmark[mpHands.HandLandmark.INDEX_FINGER_TIP]
        middle_finger_tip = hand_landmarks.landmark[mpHands.HandLandmark.MIDDLE_FINGER_TIP]
        thumb_tip = hand_landmarks.landmark[mpHands.HandLandmark.THUMB_TIP]
        pinky_tip = hand_landmarks.landmark[mpHands.HandLandmark.PINKY_TIP]
        return index_finger_tip, middle_finger_tip, thumb_tip, pinky_tip
    return None, None, None, None

# Function to detect scroll gesture
def is_scroll(landmark_list, frame):
    index_middle_dist = get_distance(landmark_list[8], landmark_list[12])
    scroll_buffer.append(index_middle_dist)
    avg_scroll_dist = np.mean(scroll_buffer)
    cv2.putText(frame, f"Scroll Distance: {avg_scroll_dist:.3f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return avg_scroll_dist < 0.05, avg_scroll_dist  # Adjust threshold based on your need

# Function to detect click gesture
def is_click(landmark_list, frame):
    thumb_index_dist = get_distance(landmark_list[4], landmark_list[8])
    click_buffer.append(thumb_index_dist)
    avg_click_dist = np.mean(click_buffer)
    cv2.putText(frame, f"Click Distance: {avg_click_dist:.3f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return avg_click_dist < 0.04  # Adjust threshold based on your need

# Function to detect double click gesture
def is_double_click(landmark_list, prev_click_time, frame):
    if is_click(landmark_list, frame):
        current_time = time.time()
        if current_time - prev_click_time < 0.5:  # Double click detection threshold
            return True, current_time
        return False, current_time
    return False, prev_click_time

# Function to detect zoom gesture
def is_zoom(landmark_list, frame):
    thumb_index_dist = get_distance(landmark_list[4], landmark_list[8])
    zoom_buffer.append(thumb_index_dist)
    avg_zoom_dist = np.mean(zoom_buffer)
    cv2.putText(frame, f"Zoom Distance: {avg_zoom_dist:.3f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return 0.01 < avg_zoom_dist < 0.02, avg_zoom_dist  # Adjust threshold to avoid accidental zoom

# Function to detect tab switching gesture
def is_tab_switch(landmark_list, frame):
    thumb_pinky_dist = get_distance(landmark_list[4], landmark_list[20])
    tab_switch_buffer.append(thumb_pinky_dist)
    avg_tab_switch_dist = np.mean(tab_switch_buffer)
    cv2.putText(frame, f"Tab Switch Distance: {avg_tab_switch_dist:.3f}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return avg_tab_switch_dist > 0.2  # Increase threshold to avoid accidental tab switching

# Function to map hand coordinates to screen coordinates
def map_coordinates(x, y, frame_width, frame_height):
    return int(x * screen_width), int(y * screen_height)

# Function to smooth cursor movement
def smooth_movement(prev_cursor, new_cursor, smoothing_factor=0.2):
    return (
        int(prev_cursor[0] + smoothing_factor * (new_cursor[0] - prev_cursor[0])),
        int(prev_cursor[1] + smoothing_factor * (new_cursor[1] - prev_cursor[1])),
    )

# Function to detect gesture and perform corresponding action
def detect_gesture(frame, landmark_list, processed, prev_cursor, prev_click_time):
    if len(landmark_list) >= 21:
        index_finger_tip, middle_finger_tip, thumb_tip, pinky_tip = find_finger_tips(processed)
        if index_finger_tip and middle_finger_tip and thumb_tip and pinky_tip:
            # Move cursor with index finger
            new_cursor_x, new_cursor_y = map_coordinates(index_finger_tip.x, index_finger_tip.y, frame.shape[1], frame.shape[0])
            cursor_x, cursor_y = smooth_movement(prev_cursor, (new_cursor_x, new_cursor_y))
            pyautogui.moveTo(cursor_x, cursor_y)

            # Apply gesture consistency: check if gesture persists for multiple frames
            scroll_detected, avg_scroll_dist = is_scroll(landmark_list, frame)
            if scroll_detected:
                if index_finger_tip.y < middle_finger_tip.y:  # Scroll up
                    pyautogui.scroll(20)  # Adjust the scrolling increment as needed
                    cv2.putText(frame, "Scrolling Up", (180, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                elif index_finger_tip.y > middle_finger_tip.y:  # Scroll down
                    pyautogui.scroll(-20)  # Adjust the scrolling increment as needed
                    cv2.putText(frame, "Scrolling Down", (180, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:  # Pause scrolling
                    cv2.putText(frame, "Scrolling Paused", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            else:
                click_detected = is_click(landmark_list, frame)
                if click_detected:
                    pyautogui.click()
                    cv2.putText(frame, "Click", (180, 220), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                double_click_detected, prev_click_time = is_double_click(landmark_list, prev_click_time, frame)
                if double_click_detected:
                    pyautogui.doubleClick()
                    cv2.putText(frame, "Double Click", (180, 260), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

                zoom_detected, avg_zoom_dist = is_zoom(landmark_list, frame)
                if zoom_detected:
                    if avg_zoom_dist < 0.015:  # Zoom in (adjusted for better accuracy)
                        pyautogui.hotkey('ctrl', '+')
                        cv2.putText(frame, "Zooming In", (180, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    elif avg_zoom_dist < 0.02:  # Zoom out (adjusted for better accuracy)
                        pyautogui.hotkey('ctrl', '-')
                        cv2.putText(frame, "Zooming Out", (180, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                
                tab_switch_detected = is_tab_switch(landmark_list, frame)
                if tab_switch_detected:
                    pyautogui.hotkey('ctrl', 'tab')  # Switch to next tab
                    cv2.putText(frame, "Switching Tab", (180, 340), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
            
            return (cursor_x, cursor_y), prev_click_time
    return prev_cursor, prev_click_time

# Function to initialize camera and perform hand gesture recognition
def MCV():
    cap = cv2.VideoCapture(0)
    prev_cursor = (0, 0)
    prev_click_time = time.time()

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            frameRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            processed = hands.process(frameRGB)

            landmark_list = []
            if processed.multi_hand_landmarks:
                hand_landmarks = processed.multi_hand_landmarks[0]  # Assuming only one hand is detected
                draw.draw_landmarks(frame, hand_landmarks, mpHands.HAND_CONNECTIONS)
                for lm in hand_landmarks.landmark:
                    landmark_list.append((lm.x, lm.y))

            prev_cursor, prev_click_time = detect_gesture(frame, landmark_list, processed, prev_cursor, prev_click_time)

            cv2.imshow('Hand Gesture Control', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

# Main function (no longer runs at import)
if __name__ == "__main__":
    MCV()
