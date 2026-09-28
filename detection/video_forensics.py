"""
Forensic analysis for video: multi-frame consistency stats (brightness,
sharpness, noise, frame-to-frame difference), Error Level Analysis on the
representative frame, and Grad-CAM for the video model's nested
EfficientNetB0 backbone.
"""
import os
import cv2
import numpy as np
import tensorflow as tf
from PIL import Image, ImageChops, ImageEnhance

from .video_ml import get_video_model, VIDEO_IMG_SIZE


def forensic_video_analysis(video_path, sample_count=20):
    """Samples frames evenly across the video and computes consistency stats."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise ValueError("Video contains no readable frames.")

    frame_indices = np.linspace(0, total_frames - 1, min(sample_count, total_frames), dtype=int)

    brightness_values, sharpness_values, noise_values, frame_differences = [], [], [], []
    previous_gray = None
    valid_frames = 0

    for index in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ret, frame = cap.read()
        if not ret:
            continue
        valid_frames += 1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        brightness_values.append(float(np.mean(gray)))
        sharpness_values.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        noise = float(np.std(gray.astype(np.float32) - blur.astype(np.float32)))
        noise_values.append(noise)

        if previous_gray is not None:
            frame_differences.append(float(np.mean(cv2.absdiff(gray, previous_gray))))
        previous_gray = gray

    cap.release()

    def safe_mean(values):
        return float(np.mean(values)) if values else 0.0

    def safe_std(values):
        return float(np.std(values)) if values else 0.0

    return {
        "frames_analyzed": valid_frames,
        "average_brightness": round(safe_mean(brightness_values), 4),
        "brightness_std": round(safe_std(brightness_values), 4),
        "average_sharpness": round(safe_mean(sharpness_values), 4),
        "sharpness_std": round(safe_std(sharpness_values), 4),
        "average_noise": round(safe_mean(noise_values), 4),
        "noise_std": round(safe_std(noise_values), 4),
        "average_frame_difference": round(safe_mean(frame_differences), 4),
    }


def generate_ela_image(image_path, output_path, quality=90, scale=15):
    """Same Error Level Analysis technique used for images, applied to a frame."""
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


try:
    import keras
except ImportError:
    from tensorflow import keras

def generate_video_gradcam(normalized_frame, output_path, img_size=VIDEO_IMG_SIZE, alpha=0.4):
    """
    Grad-CAM for the nested Sequential(EfficientNetB0 -> GAP -> Dropout ->
    Dense -> Dropout -> Dense) architecture. We build a sub-model on the
    backbone's last conv layer, then manually replay the classification
    head inside the gradient tape so gradients flow end-to-end.
    """
    model = get_video_model()
    backbone = model.get_layer("efficientnetb0")
    target_layer = backbone.get_layer("top_activation")

    grad_model = keras.models.Model(
        inputs=backbone.input,
        outputs=[target_layer.output, backbone.output],
    )

    image_tensor = tf.convert_to_tensor(normalized_frame, dtype=tf.float32)
    image_tensor = tf.expand_dims(image_tensor, axis=0)

    with tf.GradientTape() as tape:
        conv_outputs, backbone_output = grad_model(image_tensor, training=False)

        x = backbone_output
        for layer in model.layers[1:]:
            x = layer(x, training=False)

        loss = x[:, 0]

    grads = tape.gradient(loss, conv_outputs)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))

    conv_outputs = conv_outputs[0]
    heatmap = conv_outputs @ pooled_grads[..., tf.newaxis]
    heatmap = tf.squeeze(heatmap)
    heatmap = tf.maximum(heatmap, 0) / (tf.math.reduce_max(heatmap) + 1e-8)
    heatmap = heatmap.numpy()

    heatmap_img = Image.fromarray(np.uint8(255 * heatmap)).resize((img_size, img_size))
    heatmap_arr = np.asarray(heatmap_img)

    colored = np.zeros((img_size, img_size, 3), dtype=np.uint8)
    colored[..., 0] = heatmap_arr
    colored[..., 1] = np.clip(heatmap_arr.astype(np.int16) - 80, 0, 255)
    colored_img = Image.fromarray(colored).convert("RGB")

    base_img = Image.fromarray(
        np.uint8(normalized_frame * 255)
    ).resize((img_size, img_size))
    overlay = Image.blend(base_img, colored_img, alpha=alpha)
    overlay.save(output_path, "PNG")

    return {"focus_area_pct": round(float((heatmap_arr > 128).mean() * 100), 2)}
