"""
Lazily loads the trained EfficientNetB0 deepfake detection model
(only once, on first use) and exposes predict_image().
"""
import threading
import tensorflow as tf
import numpy as np
from PIL import Image
from django.conf import settings

try:
    import keras
except ImportError:
    from tensorflow import keras

def load_img(path, target_size=None, **kwargs):
    img = Image.open(path).convert("RGB")
    if target_size:
        img = img.resize((target_size[1], target_size[0]), Image.Resampling.BILINEAR)
    return img

def img_to_array(img):
    return np.asarray(img, dtype=np.float32)

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                print(f"[MODEL] Loading deepfake detection model from {settings.MODEL_PATH} ...")
                _model = keras.models.load_model(settings.MODEL_PATH)
                print("[MODEL] Model loaded successfully.")
    return _model


def predict_image(image_path):
    model = get_model()
    img_size = settings.IMG_SIZE

    img = load_img(image_path, target_size=(img_size, img_size), color_mode="rgb")
    img_array = img_to_array(img)
    img_array = tf.convert_to_tensor(img_array, dtype=tf.float32)
    img_array = tf.expand_dims(img_array, axis=0)

    probability = float(model(img_array, training=False)[0][0])

    # Training labels: fake = 0, real = 1
    if probability >= 0.5:
        prediction = "REAL"
        confidence = probability * 100
    else:
        prediction = "FAKE"
        confidence = (1 - probability) * 100

    return {
        "prediction": prediction,
        "confidence": round(confidence, 2),
        "probability": round(probability, 6),
    }


def get_last_conv_layer_name(model=None):
    model = model or get_model()
    try:
        for layer in reversed(model.layers):
            shape = layer.output_shape
            if isinstance(shape, tuple) and len(shape) == 4:
                return layer.name
    except Exception:
        pass
    return "top_conv"
