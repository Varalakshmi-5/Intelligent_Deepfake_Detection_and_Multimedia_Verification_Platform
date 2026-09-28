"""
Lazily loads the trained text AI-detection model (TF-IDF + Logistic
Regression, 100% test accuracy on held-out data, ROC-AUC 1.0000) and
exposes metadata analysis, prediction, and word-contribution helpers.

Label convention: 0 = AI/FAKE, 1 = HUMAN/REAL.
"""
import re
import threading
import joblib
from django.conf import settings

_model = None
_vectorizer = None
_lock = threading.Lock()

MIN_TEXT_LENGTH = 20  # characters


def _load():
    global _model, _vectorizer
    if _model is None or _vectorizer is None:
        with _lock:
            if _model is None or _vectorizer is None:
                print(f"[TEXT MODEL] Loading from {settings.TEXT_MODEL_PATH} ...")
                _model = joblib.load(settings.TEXT_MODEL_PATH)
                _vectorizer = joblib.load(settings.TEXT_VECTORIZER_PATH)
                print("[TEXT MODEL] Loaded successfully.")
    return _model, _vectorizer


def get_text_model():
    model, _ = _load()
    return model


def get_text_vectorizer():
    _, vectorizer = _load()
    return vectorizer


def analyze_text_metadata(text):
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    word_count = len(words)
    character_count = len(text)
    sentence_count = len(sentences)

    avg_word_length = (
        sum(len(word) for word in words) / word_count if word_count else 0
    )
    avg_sentence_length = (
        word_count / sentence_count if sentence_count else 0
    )

    unique_words = len(set(word.lower() for word in words))
    vocabulary_ratio = (unique_words / word_count) if word_count else 0

    uppercase_count = sum(1 for c in text if c.isupper())
    digit_count = sum(1 for c in text if c.isdigit())
    punctuation_count = sum(1 for c in text if c in ".,!?;:'\"-()[]{}")

    return {
        "character_count": character_count,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "average_word_length": round(avg_word_length, 2),
        "average_sentence_length": round(avg_sentence_length, 2),
        "unique_words": unique_words,
        "vocabulary_richness": round(vocabulary_ratio, 4),
        "uppercase_count": uppercase_count,
        "digit_count": digit_count,
        "punctuation_count": punctuation_count,
    }


def predict_text(text):
    model, vectorizer = _load()
    text_features = vectorizer.transform([text])

    prediction_value = int(model.predict(text_features)[0])
    probabilities = model.predict_proba(text_features)[0]

    fake_probability = float(probabilities[0])
    real_probability = float(probabilities[1])

    if prediction_value == 0:
        prediction = "FAKE"
        prediction_label = "AI / FAKE"
        confidence = fake_probability * 100
        verdict = "LIKELY AI-GENERATED"
    else:
        prediction = "REAL"
        prediction_label = "HUMAN / REAL"
        confidence = real_probability * 100
        verdict = "LIKELY HUMAN-WRITTEN"

    return {
        "prediction": prediction,
        "prediction_label": prediction_label,
        "confidence": round(confidence, 2),
        "fake_probability": round(fake_probability, 4),
        "real_probability": round(real_probability, 4),
        "verdict": verdict,
    }


def get_top_contributing_words(text, top_n=8):
    """
    Interpretability: for each word/n-gram present in the text, computes
    its contribution to the HUMAN-vs-AI decision (TF-IDF weight × logistic
    regression coefficient). Positive contributions push toward
    HUMAN/REAL, negative push toward AI/FAKE.
    """
    model, vectorizer = _load()
    text_features = vectorizer.transform([text])
    feature_names = vectorizer.get_feature_names_out()
    coefficients = model.coef_[0]

    nonzero_indices = text_features.nonzero()[1]
    if len(nonzero_indices) == 0:
        return {"human_indicative": [], "ai_indicative": []}

    contributions = []
    for idx in nonzero_indices:
        tfidf_value = text_features[0, idx]
        contribution = float(tfidf_value * coefficients[idx])
        contributions.append((feature_names[idx], contribution))

    contributions.sort(key=lambda pair: pair[1], reverse=True)

    human_indicative = [
        {"term": term, "weight": round(score, 4)}
        for term, score in contributions if score > 0
    ][:top_n]
    ai_indicative = [
        {"term": term, "weight": round(score, 4)}
        for term, score in reversed(contributions) if score < 0
    ][:top_n]

    return {"human_indicative": human_indicative, "ai_indicative": ai_indicative}
