"""
Forensic visualizations for the Forensic Analysis tab:
  1. Error Level Analysis (ELA) - highlights regions with inconsistent
     JPEG compression, a classic tampering/splicing indicator.
  2. Grad-CAM - highlights the image regions the AI model focused on
     when making its REAL/FAKE decision.
"""
import os
import numpy as np
import tensorflow as tf
from PIL import Image, ImageChops, ImageEnhance
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

from .ml import get_model, get_last_conv_layer_name


def generate_ela_image(image_path, output_path, quality=90, scale=15):
    original = Image.open(image_path).convert("RGB")

    tmp_path = output_path + ".tmp.jpg"
    original.save(tmp_path, "JPEG", quality=quality)
    resaved = Image.open(tmp_path)

    diff = ImageChops.difference(original, resaved)
    extrema = diff.getextrema()
    max_diff = max(ex[1] for ex in extrema) or 1

    ela_scale = min(255.0 / max_diff, scale)
    ela_image = ImageEnhance.Brightness(diff).enhance(ela_scale)
    ela_image.save(output_path, "PNG")

    os.remove(tmp_path)

    diff_array = np.asarray(diff, dtype=np.float32)
    irregularity_score = float(min(100.0, (diff_array.std() / 255.0) * 400))

    return {"irregularity_score": round(irregularity_score, 2)}


def generate_gradcam(image_path, output_path, img_size=224, alpha=0.4):
    model = get_model()
    last_conv_layer_name = get_last_conv_layer_name(model)

    img = load_img(image_path, target_size=(img_size, img_size), color_mode="rgb")
    img_array = img_to_array(img)
    img_tensor = tf.expand_dims(tf.convert_to_tensor(img_array, dtype=tf.float32), axis=0)

    grad_model = keras.models.Model(
        inputs=model.inputs,
        outputs=[model.get_layer(last_conv_layer_name).output, model.output],
    )

    with tf.GradientTape() as tape:
        conv_output, predictions = grad_model(img_tensor)
        loss = predictions[:, 0]

    grads = tape.gradient(loss, conv_output)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))

    conv_output = conv_output[0]
    heatmap = conv_output @ pooled_grads[..., tf.newaxis]
    heatmap = tf.squeeze(heatmap)
    heatmap = tf.maximum(heatmap, 0) / (tf.math.reduce_max(heatmap) + 1e-8)
    heatmap = heatmap.numpy()

    heatmap_img = Image.fromarray(np.uint8(255 * heatmap)).resize((img_size, img_size))
    heatmap_arr = np.asarray(heatmap_img)

    colored = np.zeros((img_size, img_size, 3), dtype=np.uint8)
    colored[..., 0] = heatmap_arr
    colored[..., 1] = np.clip(heatmap_arr.astype(np.int16) - 80, 0, 255)
    colored_img = Image.fromarray(colored).convert("RGB")

    base_img = Image.open(image_path).convert("RGB").resize((img_size, img_size))
    overlay = Image.blend(base_img, colored_img, alpha=alpha)
    overlay.save(output_path, "PNG")

    return {"focus_area_pct": round(float((heatmap_arr > 128).mean() * 100), 2)}
