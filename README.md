# EscapeFromAI
GenAI project INF-3600
## Setup

### Download MediaPipe Model

Download the MediaPipe gesture recognizer model required for hand gesture recognition:

```
https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task
```

### Create Model Directory

Create the required directory structure for the model:

```bash
mkdir -p models/hand_gesture
```

Then place the downloaded `.task` file in the `models/hand_gesture/` folder.