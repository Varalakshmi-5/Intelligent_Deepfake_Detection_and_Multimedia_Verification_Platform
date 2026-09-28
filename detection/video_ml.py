"""
Lazily loads the trained video deepfake detection model
(EfficientNetB0 backbone, fine-tuned on FaceForensics++ C23) and
exposes frame extraction + prediction helpers.

Model output convention: 0 = REAL, 1 = FAKE (probability of FAKE).
Decision threshold: 0.62 (tuned during training, not the default 0.5).
"""
import os
import threading
import cv2
import numpy as np
import tensorflow as tf
from django.conf import settings

try:
    import keras
except ImportError:
    from tensorflow import keras

_model = None
_lock = threading.Lock()

VIDEO_IMG_SIZE = 224
VIDEO_THRESHOLD = 0.62


def get_video_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                print(f"[VIDEO MODEL] Loading from {settings.VIDEO_MODEL_PATH} ...")
                _model = keras.models.load_model(settings.VIDEO_MODEL_PATH)
                print("[VIDEO MODEL] Loaded successfully.")
    return _model


def get_video_metadata(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = (total_frames / fps) if fps > 0 else 0
    cap.release()

    file_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)

    return {
        "total_frames": total_frames,
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "duration_sec": round(duration, 2),
        "file_size_mb": file_size_mb,
    }


def extract_middle_frame(video_path, total_frames=None):
    """Returns the middle frame as a BGR numpy array (OpenCV format)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")

    if total_frames is None:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    middle_index = max(total_frames // 2, 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, middle_index)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise ValueError("Could not extract a frame from this video.")

    return frame  # BGR


def preprocess_frame(frame_bgr, size=VIDEO_IMG_SIZE):
    """BGR uint8 frame -> normalized RGB float32 tensor, shape (size, size, 3)."""
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    frame_resized = cv2.resize(frame_rgb, (size, size))
    normalized = frame_resized.astype(np.float32) / 255.0
    return frame_rgb, normalized


def predict_frame(normalized_frame):
    """normalized_frame: float32 array (224,224,3), values in [0,1]."""
    model = get_video_model()
    batch = np.expand_dims(normalized_frame, axis=0)
    prediction = model.predict(batch, verbose=0)
    fake_probability = float(np.squeeze(prediction))
    real_probability = 1.0 - fake_probability

    if fake_probability >= VIDEO_THRESHOLD:
        prediction_label = "FAKE"
        confidence = fake_probability * 100
    else:
        prediction_label = "REAL"
        confidence = real_probability * 100

    return {
        "prediction": prediction_label,
        "confidence": round(confidence, 2),
        "fake_probability": round(fake_probability, 6),
        "real_probability": round(real_probability, 6),
        "threshold": VIDEO_THRESHOLD,
    }


_face_cascade = None


def detect_faces(frame_bgr):
    global _face_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    return len(faces)
