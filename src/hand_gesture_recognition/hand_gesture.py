# Hand Gesture Recognition Data Logger
# This script uses MediaPipe to recognize hand gestures from webcam input
# and allows users to capture training data for specific gestures.

import cv2
import os
import time
import json
import random
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# =============================
# Configuration & Model Paths
# =============================
# Path to the pre-trained MediaPipe gesture recognition model
MODEL_PATH = "models/hand_gesture/gesture_recognizer.task" 
# File where captured gesture data will be stored
DATA_FILE = "captured_gestures.txt"
# JSON file containing gesture labels and prompts
PROMPTS_PATH = "prompts.json"
# Number of gesture targets to show per round
TARGETS_PER_ROUND = 3

# =============================
# MediaPipe Gesture Recognition Setup
# =============================
# Load the pre-trained gesture recognition model
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
# Configure the recognizer for video mode with single hand detection
options = vision.GestureRecognizerOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.VIDEO,  # Process continuous video stream
    num_hands=1  # Detect only one hand for cleaner data logging
)
# Initialize the gesture recognizer
recognizer = vision.GestureRecognizer.create_from_options(options)

# Open connection to the default webcam (0)
cap = cv2.VideoCapture(0)

def load_labels(prompts_path: str) -> list[str]:
    """
    Load gesture labels from the prompts.json file.
    
    Args:
        prompts_path: Path to the JSON file containing gesture definitions
        
    Returns:
        A sorted list of unique gesture labels, excluding "Unknown" and "None"
    """
    try:
        with open(prompts_path, "r") as f:
            data = json.load(f)
        # Extract label values from dictionary entries that are dictionaries
        labels = [v.get("label") for v in data.values() if isinstance(v, dict)]
        # Filter out empty or generic labels
        labels = [l for l in labels if l and l not in {"Unknown", "None"}]
        return sorted(set(labels))
    except Exception:
        # Fallback to the common MediaPipe gesture set used by the prompts
        return [
            "Closed_Fist",
            "Open_Palm",
            "Pointing_Up",
            "Thumb_Down",
            "Thumb_Up",
            "Victory",
            "ILoveYou",
        ]


def new_target_queue(labels: list[str], k: int) -> list[str]:
    """
    Create a random queue of gesture targets to capture.
    
    Args:
        labels: Available gesture labels to sample from
        k: Number of targets to generate
        
    Returns:
        A list of k randomly selected gesture labels
    """
    if not labels:
        # No labels available; default to Thumb_Up
        return ["Thumb_Up"] * k
    if len(labels) >= k:
        # Enough unique labels; sample without replacement
        return random.sample(labels, k)
    # Not enough unique labels; allow repeats for variety
    return [random.choice(labels) for _ in range(k)]


# =============================
# Initialize Data Logger State
# =============================
# Load gesture labels from configuration
labels_pool = load_labels(PROMPTS_PATH)
# Create initial queue of target gestures to capture
target_queue = new_target_queue(labels_pool, TARGETS_PER_ROUND)
# Status message displayed on screen
status_text = ""
# Timestamp until which to display the status message (in milliseconds)
status_until_ms = 0

# Print keyboard shortcuts for the user
print("Press 'C' to capture the shown label | 'N' to skip round | 'Q' to quit.")

# =============================
# Main Video Processing Loop
# =============================
while cap.isOpened():
    # Capture frame from webcam
    success, frame = cap.read()
    if not success: break

    # Flip frame horizontally for mirror effect (more intuitive for users)
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    
    # Convert BGR (OpenCV default) to RGB (MediaPipe required format)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # Create MediaPipe Image object
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # Get current timestamp in milliseconds for gesture recognition
    frame_timestamp_ms = int(time.time() * 1000)
    # Run gesture recognition on the current frame
    result = recognizer.recognize_for_video(mp_image, frame_timestamp_ms)

    # Extract gesture and hand landmarks from recognition result
    current_gesture = "None"
    current_landmarks = None

    if result.hand_landmarks:
        # If a hand is detected, extract the recognized gesture
        if result.gestures:
            current_gesture = result.gestures[0][0].category_name
            # Get the 21 3D landmark points of the detected hand
            current_landmarks = result.hand_landmarks[0]

        # Visualize detected hand landmarks as green dots on the frame
        if current_landmarks:
            for landmark in current_landmarks:
                # Convert normalized coordinates (0-1) to pixel coordinates
                cx, cy = int(landmark.x * w), int(landmark.y * h)
                # Draw small circle at each landmark position
                cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)


    # =============================
    # Display UI Overlay on Frame
    # =============================
    # Get the current target gesture from the queue
    target_label = target_queue[0] if target_queue else "None"
    # Display currently recognized gesture in green
    cv2.putText(frame, f"Sign: {current_gesture}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    # Display target gesture to capture in yellow
    cv2.putText(frame, f"Target: {target_label}", (20, 95),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)

    # Display the queue of remaining targets (up to TARGETS_PER_ROUND)
    # First target is highlighted in yellow, others in gray
    y0 = 135
    for i, t in enumerate(target_queue[:TARGETS_PER_ROUND]):
        # Highlight the current target (first in queue)
        color = (255, 255, 0) if i == 0 else (200, 200, 200)
        cv2.putText(frame, f"{i+1}. {t}", (20, y0 + i * 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    # Display temporary status messages (e.g., "Captured: Thumb_Up")
    now_ms = int(time.time() * 1000)
    if status_text and now_ms < status_until_ms:
        # Show status message in cyan at bottom of frame
        cv2.putText(frame, status_text, (20, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

    # Display the processed frame in a window
    cv2.imshow("Sign Data Logger", frame)

    # Wait 1ms for keyboard input; get only the lower 8 bits (ASCII value)
    key = cv2.waitKey(1) & 0xFF

    # =============================
    # Handle Keyboard Input
    # =============================
    # 'C' key: Attempt to capture the current gesture
    if key == ord('c'):
        # Check if there are any targets left in the queue
        if not target_queue:
            # Reset queue when empty (shouldn't reach here due to break statement)
            target_queue = new_target_queue(labels_pool, TARGETS_PER_ROUND)
            status_text = "New targets"
            status_until_ms = int(time.time() * 1000) + 1200
            continue

        # Get the gesture we need to capture
        required = target_queue[0]

        # Validate that a hand and gesture were detected
        if current_gesture == "None" or not current_landmarks:
            status_text = "No hand detected"
            status_until_ms = int(time.time() * 1000) + 1200
            print("⚠️ No hand detected! Nothing to save.")
            continue

        # Check if the current gesture matches the target
        if current_gesture != required:
            status_text = f"Wrong: need {required}"
            status_until_ms = int(time.time() * 1000) + 1200
            print(f"⚠️ Wrong gesture. Showing {required}, got {current_gesture}.")
            continue

        # If all checks pass, save the gesture data to file
        if current_gesture != "None" and current_landmarks:
            with open(DATA_FILE, "a") as f:
                # Get human-readable timestamp
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Format: timestamp | label | 21 hand landmarks (x,y,z coordinates)
                # Option B: Save the name + all 21 coordinates (x,y,z)
                coords = [f"({l.x:.3f},{l.y:.3f},{l.z:.3f})" for l in current_landmarks]
                data_string = f"{ts} | Label: {current_gesture} | Landmarks: {' '.join(coords)}\n"
                
                f.write(data_string)
                
            print(f"✅ Saved SIGN: {current_gesture} to {DATA_FILE}")
            status_text = f"Captured: {current_gesture}"
            status_until_ms = int(time.time() * 1000) + 1200

            # Remove the captured target from the queue
            target_queue.pop(0)
            # If all targets in this round are captured, end the round
            if not target_queue:
                break
                # Generate new targets for the next round (code after break is unreachable)
                target_queue = new_target_queue(labels_pool, TARGETS_PER_ROUND)
                status_text = "Round complete. New targets"
                status_until_ms = int(time.time() * 1000) + 1500

    # 'N' key: Skip the current round and generate new targets
    elif key == ord('n'):
        target_queue = new_target_queue(labels_pool, TARGETS_PER_ROUND)
        status_text = "Skipped. New targets"
        status_until_ms = int(time.time() * 1000) + 1200

    # 'Q' key: Quit the program
    elif key == ord('q'):
        break

# =============================
# Cleanup and Close Resources
# =============================
# Release the webcam resource
cap.release()
# Close all OpenCV windows
cv2.destroyAllWindows()
# Close the gesture recognizer
recognizer.close()
