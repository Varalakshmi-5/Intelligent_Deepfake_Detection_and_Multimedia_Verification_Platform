"""
Forensic visualizations for audio: waveform plot, colorized Log-Mel
spectrogram, and a Grad-CAM attention overlay on the spectrogram —
all rendered with PIL/numpy only (no matplotlib dependency).
"""
import numpy as np
import tensorflow as tf
from PIL import Image, ImageDraw

from .audio_ml import get_audio_model, AUDIO_LAST_CONV_LAYER

# App theme colors
BG_COLOR = (10, 14, 20)
ACCENT_COLOR = (62, 230, 208)
DIM_ACCENT = (28, 70, 66)


def _colorize(value_0_1):
    """Maps a 0-1 intensity to an (R,G,B) tuple: dark navy -> teal -> white."""
    v = np.clip(value_0_1, 0.0, 1.0)
    dark = np.array([10, 14, 20], dtype=np.float32)
    mid = np.array([62, 230, 208], dtype=np.float32)
    light = np.array([255, 255, 255], dtype=np.float32)

    out = np.empty(v.shape + (3,), dtype=np.float32)
    lower = v < 0.6
    t_lower = np.clip(v / 0.6, 0, 1)
    t_upper = np.clip((v - 0.6) / 0.4, 0, 1)

    for c in range(3):
        low_val = dark[c] + (mid[c] - dark[c]) * t_lower
        high_val = mid[c] + (light[c] - mid[c]) * t_upper
        out[..., c] = np.where(lower, low_val, high_val)

    return np.clip(out, 0, 255).astype(np.uint8)


def generate_waveform_image(audio, sr, output_path, width=1000, height=260):
    """Draws a peak-envelope waveform on a dark background matching the app theme."""
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    mid_y = height // 2

    if len(audio) == 0:
        img.save(output_path, "PNG")
        return

    bucket_size = max(len(audio) // width, 1)
    peaks = []
    for i in range(width):
        start = i * bucket_size
        end = min(start + bucket_size, len(audio))
        if start >= len(audio):
            peaks.append(0.0)
            continue
        chunk = audio[start:end]
        peaks.append(float(np.max(np.abs(chunk))) if len(chunk) else 0.0)

    max_peak = max(peaks) or 1.0
    for x, p in enumerate(peaks):
        norm = (p / max_peak) if max_peak > 0 else 0
        bar_height = int(norm * (height * 0.42))
        draw.line([(x, mid_y - bar_height), (x, mid_y + bar_height)], fill=ACCENT_COLOR, width=1)

    draw.line([(0, mid_y), (width, mid_y)], fill=DIM_ACCENT, width=1)
    img.save(output_path, "PNG")


def generate_spectrogram_image(spectrogram, output_path, scale=3):
    """spectrogram: (128, 256, 3) float32, values 0-255 (all channels identical)."""
    gray = spectrogram[:, :, 0] / 255.0
    gray = np.flipud(gray)  # low frequencies at the bottom, like librosa's origin='lower'

    colored = _colorize(gray)
    img = Image.fromarray(colored, "RGB")
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(output_path, "PNG")


try:
    import keras
except ImportError:
    from tensorflow import keras

def generate_audio_gradcam(spectrogram, output_path, layer_name=AUDIO_LAST_CONV_LAYER, scale=3):
    """
    Grad-CAM for the Sequential CNN audio model. Rebuilds a fresh functional
    graph so intermediate conv activations can be captured (mirrors the
    "Keras Sequential fix" approach used in the training notebook).
    """
    model = get_audio_model()
    input_tensor = np.expand_dims(spectrogram, axis=0).astype(np.float32)

    inputs = keras.Input(shape=(128, 256, 3))
    x = inputs
    conv_output = None
    for layer in model.layers:
        if isinstance(layer, keras.layers.InputLayer):
            continue
        x = layer(x)
        if layer.name == layer_name:
            conv_output = x
    final_output = x

    if conv_output is None:
        raise ValueError(f"Layer '{layer_name}' not found in audio model.")

    grad_model = keras.models.Model(inputs=inputs, outputs=[conv_output, final_output])

    with tf.GradientTape() as tape:
        conv_features, prediction = grad_model(input_tensor, training=False)
        probability = prediction[:, 0]

    gradients = tape.gradient(probability, conv_features)
    pooled_gradients = tf.reduce_mean(gradients, axis=(1, 2))

    conv_features = conv_features[0]
    pooled_gradients = pooled_gradients[0]

    heatmap = tf.reduce_sum(conv_features * pooled_gradients, axis=-1)
    heatmap = tf.maximum(heatmap, 0)
    max_value = tf.reduce_max(heatmap)
    if float(max_value) > 0:
        heatmap = heatmap / max_value
    heatmap = heatmap.numpy()  # shape (16, 32)

    # Resize heatmap to spectrogram size and overlay on the colorized spectrogram
    heatmap_img = Image.fromarray(np.uint8(255 * heatmap)).resize((256, 128), Image.BILINEAR)
    heatmap_resized = np.asarray(heatmap_img).astype(np.float32) / 255.0
    heatmap_resized = np.flipud(heatmap_resized)

    base_gray = np.flipud(spectrogram[:, :, 0] / 255.0)
    base_colored = _colorize(base_gray).astype(np.float32)

    # Warm overlay (orange/red) where the model focused attention
    overlay = np.zeros_like(base_colored)
    overlay[..., 0] = 255  # red
    overlay[..., 1] = 120  # some green -> orange

    alpha = (heatmap_resized[..., None] * 0.55)
    blended = base_colored * (1 - alpha) + overlay * alpha
    blended = np.clip(blended, 0, 255).astype(np.uint8)

    img = Image.fromarray(blended, "RGB")
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(output_path, "PNG")

    focus_area_pct = round(float((heatmap_resized > 0.5).mean() * 100), 2)
    return {"focus_area_pct": focus_area_pct}
