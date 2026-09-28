"""
Facial Biometric Matching Utility functions.
Computes Euclidean distance between 128-dimensional facial feature vectors
and searches existing registered users to detect duplicate account creation.
"""
import json
import math
from django.contrib.auth import get_user_model

User = get_user_model()


def calculate_vector_distance(vec1, vec2):
    """Calculates Euclidean distance between two numeric feature arrays."""
    if len(vec1) != len(vec2):
        return 999.0
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))


def find_matching_face_user(candidate_vector, threshold=1.20, current_email=None):
    """
    Searches all existing verified users with face_registered=True.
    Returns (matching_user, min_distance) if vector distance < threshold.
    """
    if not candidate_vector or not isinstance(candidate_vector, list):
        return None, None

    registered_users = User.objects.filter(face_registered=True, is_verified=True).exclude(face_descriptor__isnull=True).exclude(face_descriptor="")
    if current_email:
        registered_users = registered_users.exclude(email=current_email.lower())

    best_match = None
    min_dist = 999.0

    for user in registered_users:
        try:
            stored_vector = json.loads(user.face_descriptor)
            dist = calculate_vector_distance(candidate_vector, stored_vector)
            if dist < min_dist:
                min_dist = dist
                best_match = user
        except Exception:
            continue

    if best_match and min_dist <= threshold:
        return best_match, min_dist

    return None, min_dist

