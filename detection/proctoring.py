"""
AI Online Interview Proctoring & Environment Integrity Module.
Provides object detection for interview surroundings (cell phone, book, notebook,
earphones/headphones, secondary person, pen, pencil, cup), centroid spatial distance
calculation between the candidate's face and surrounding objects, and warning flag creation.
"""
import math
import numpy as np
import cv2

# Prohibited items that trigger RED warnings & integrity drops
PROHIBITED_CLASSES = {
    "cell phone": {"severity": "HIGH", "warning": "Unauthorized Cell Phone / Mobile Device Detected"},
    "mobile phone": {"severity": "HIGH", "warning": "Unauthorized Cell Phone / Mobile Device Detected"},
    "book": {"severity": "HIGH", "warning": "Unauthorized Book / Reference Material Detected"},
    "notebook": {"severity": "HIGH", "warning": "Unauthorized Notebook / Cheatsheet Detected"},
    "laptop": {"severity": "MEDIUM", "warning": "Secondary Screen / Laptop Detected"},
    "extra_person": {"severity": "CRITICAL", "warning": "Unauthorized Secondary Person Detected in Room"},
    "earphone": {"severity": "HIGH", "warning": "Earphone / Bluetooth Audio Aid Detected"},
}

# Permitted / Neutral objects
PERMITTED_CLASSES = {
    "pen": "Permitted writing tool",
    "pencil": "Permitted writing tool",
    "cup": "Permitted beverage mug",
    "bottle": "Permitted water bottle",
    "chair": "Furniture",
}


def calculate_centroid(bbox):
    """
    bbox format: [ymin, xmin, ymax, xmax] or [x, y, w, h] normalized or pixel coordinates.
    Returns (center_x, center_y).
    """
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def estimate_distance_cm(face_centroid, object_centroid, frame_width=640, camera_fov_factor=0.15):
    """
    Calculates pixel distance between face centroid and object centroid,
    and estimates physical distance in centimeters based on camera FOV scaling.
    """
    fx, fy = face_centroid
    ox, oy = object_centroid
    pixel_dist = math.hypot(ox - fx, oy - fy)
    
    # Approximate physical conversion: 100px on 640px wide camera ~ 15-20cm depending on distance to camera
    cm_estimate = round(pixel_dist * camera_fov_factor, 1)
    return pixel_dist, max(cm_estimate, 5.0)


def evaluate_proctoring_frame(detections, frame_width=640, frame_height=480):
    """
    Evaluates a frame's detected objects list:
    detections: list of dicts:
      [{"class": "cell phone", "confidence": 0.88, "bbox": [x1, y1, x2, y2]}, ...]
    
    Returns:
      {
        "integrity_score": int (0-100),
        "violations": [...],
        "allowed_objects": [...],
        "warnings": [...],
        "faces_detected": int,
        "closest_prohibited_distance_cm": float or None,
        "is_clean": bool
      }
    """
    faces = [d for d in detections if d["class"].lower() in ("person", "face")]
    prohibited_found = []
    allowed_found = []
    warnings = []
    
    face_centroid = None
    if faces:
        # Use first/largest face as candidate
        main_face = max(faces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
        face_centroid = calculate_centroid(main_face["bbox"])
    
    # Check for multiple persons
    if len(faces) > 1:
        warnings.append({
            "code": "MULTIPLE_PERSONS",
            "severity": "CRITICAL",
            "message": f"⚠️ Multiple Persons Detected ({len(faces)} people in camera view)",
            "distance_cm": None,
        })
    elif len(faces) == 0:
        warnings.append({
            "code": "NO_FACE",
            "severity": "HIGH",
            "message": "⚠️ Candidate Not Visible / Face Out of Frame",
            "distance_cm": None,
        })

    closest_dist = None

    for item in detections:
        cls_name = item["class"].lower().strip()
        bbox = item["bbox"]
        conf = item["confidence"]
        
        obj_centroid = calculate_centroid(bbox)
        dist_px, dist_cm = (None, None)
        if face_centroid:
            dist_px, dist_cm = estimate_distance_cm(face_centroid, obj_centroid, frame_width=frame_width)
            if closest_dist is None or dist_cm < closest_dist:
                closest_dist = dist_cm

        if cls_name in PROHIBITED_CLASSES:
            meta = PROHIBITED_CLASSES[cls_name]
            warnings.append({
                "code": cls_name.upper().replace(" ", "_"),
                "severity": meta["severity"],
                "message": f"⚠️ {meta['warning']} ({dist_cm}cm from face)",
                "class_name": cls_name,
                "confidence": round(conf * 100, 1),
                "distance_cm": dist_cm,
                "bbox": bbox
            })
            prohibited_found.append({
                "class": cls_name,
                "confidence": round(conf * 100, 1),
                "distance_cm": dist_cm,
                "bbox": bbox
            })
        elif cls_name in PERMITTED_CLASSES:
            allowed_found.append({
                "class": cls_name,
                "confidence": round(conf * 100, 1),
                "distance_cm": dist_cm,
                "description": PERMITTED_CLASSES[cls_name]
            })

    # Calculate overall integrity score (0-100)
    penalty = 0
    for w in warnings:
        if w["severity"] == "CRITICAL":
            penalty += 40
        elif w["severity"] == "HIGH":
            penalty += 25
        elif w["severity"] == "MEDIUM":
            penalty += 15

    integrity_score = max(100 - penalty, 0)

    return {
        "integrity_score": integrity_score,
        "is_clean": len(prohibited_found) == 0 and len(faces) == 1,
        "faces_detected": len(faces),
        "violations": prohibited_found,
        "allowed_objects": allowed_found,
        "warnings": warnings,
        "closest_prohibited_distance_cm": closest_dist,
    }
