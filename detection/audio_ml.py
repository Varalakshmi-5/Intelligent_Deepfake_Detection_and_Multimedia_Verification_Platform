"""
Lazily loads the trained audio deepfake detection model (custom CNN on
Log-Mel spectrograms, 99.93% test accuracy, ROC-AUC 1.0000) and exposes
spectrogram conversion + prediction helpers.

Model output convention: sigmoid output = probability of REAL.
Decision threshold: 0.5 (standard).
"""
import os
import threading
import numpy as np
import librosa
import soundfile as sf
import tensorflow as tf
from django.conf import settings

try:
    import keras
except ImportError:
    from tensorflow import keras

_model = None
_lock = threading.Lock()

AUDIO_IMG_HEIGHT = 128
AUDIO_IMG_WIDTH = 256
AUDIO_SAMPLE_RATE = 16000
AUDIO_LAST_CONV_LAYER = "conv2d_3"


def get_audio_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                print(f"[AUDIO MODEL] Loading from {settings.AUDIO_MODEL_PATH} ...")
                _model = keras.models.load_model(settings.AUDIO_MODEL_PATH, compile=False)
                print("[AUDIO MODEL] Loaded successfully.")
    return _model


def get_audio_metadata(audio_path):
    info = sf.info(audio_path)
    file_size_kb = round(os.path.getsize(audio_path) / 1024, 2)

    return {
        "duration_sec": round(info.duration, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "subtype": info.subtype,
        "format": os.path.splitext(audio_path)[1].upper().lstrip("."),
        "file_size_kb": file_size_kb,
    }


def audio_to_spectrogram(filepath, img_height=AUDIO_IMG_HEIGHT, img_width=AUDIO_IMG_WIDTH, sample_rate=AUDIO_SAMPLE_RATE):
    """
    Converts an audio file to a normalized (img_height, img_width, 3)
    Log-Mel spectrogram, matching the exact preprocessing used during
    training (values in 0-255 range, NOT divided by 255).
    """
    audio, sr = librosa.load(filepath, sr=sample_rate, mono=True)

    mel = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_fft=1024, hop_length=256, n_mels=img_height
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)

    mel_db = mel_db - mel_db.min()
    if mel_db.max() > 0:
        mel_db = mel_db / mel_db.max()
    mel_db = mel_db * 255.0

    mel_db = tf.image.resize(
        mel_db[..., np.newaxis], [img_height, img_width]
    ).numpy().squeeze()

    mel_rgb = np.stack([mel_db, mel_db, mel_db], axis=-1)
    return mel_rgb.astype(np.float32)


def predict_audio(spectrogram):
    """spectrogram: float32 array (128, 256, 3), values in [0, 255]."""
    model = get_audio_model()
    X = np.expand_dims(spectrogram, axis=0).astype(np.float32)

    prediction = model.predict(X, verbose=0)
    real_probability = float(prediction[0][0])
    fake_probability = 1.0 - real_probability

    if real_probability >= 0.5:
        prediction_label = "REAL"
        confidence = real_probability * 100
    else:
        prediction_label = "FAKE"
        confidence = fake_probability * 100

    return {
        "prediction": prediction_label,
        "confidence": round(confidence, 2),
        "real_probability": round(real_probability, 6),
        "fake_probability": round(fake_probability, 6),
    }


def load_waveform(filepath):
    """Returns (audio_samples, sample_rate) at the file's native sample rate."""
    audio, sr = librosa.load(filepath, sr=None, mono=True)
    return audio, sr
