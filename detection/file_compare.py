"""
Compares two uploaded files: exact SHA-256 match, perceptual similarity check (for images),
alignment detection (Left, Right, Center, Justified), and multi-level feature breakdown
(Word-wise, Sentence-wise, Line-wise, Page-wise).
"""
import os
import re
import numpy as np

from PIL import Image

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .certificate import compute_file_hash
from .document_forensics import ocr_page, render_pdf_pages, load_image_as_page, TESSERACT_AVAILABLE

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp"}
TEXT_DOC_EXTENSIONS = {"pdf", "txt", "doc", "docx", "jpg", "jpeg", "png", "bmp", "webp"}


def extract_text_from_file(file_path):
    """
    Utility function to safely extract text from txt, pdf, or image files.
    """
    if not os.path.exists(file_path):
        return ""
    ext = file_path.rsplit(".", 1)[1].lower() if "." in file_path else ""

    if ext == "txt":
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""
    elif ext == "pdf":
        try:
            pages = render_pdf_pages(file_path, max_pages=10)
            texts = []
            for img, text in pages:
                if text and text.strip():
                    texts.append(text)
                elif TESSERACT_AVAILABLE:
                    ocr_t = ocr_page(img)
                    if ocr_t:
                        texts.append(ocr_t)
            return "\n".join(texts)
        except Exception:
            return ""
    elif ext in IMAGE_EXTENSIONS:
        try:
            if TESSERACT_AVAILABLE:
                pages = load_image_as_page(file_path)
                if pages:
                    img, _ = pages[0]
                    return ocr_page(img)
        except Exception:
            return ""
    return ""




def is_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in IMAGE_EXTENSIONS


def compute_average_hash(image_path, hash_size=8):
    """
    Simple, well-known perceptual hash (aHash): shrink to a small
    grayscale grid, compare each pixel to the average, encode as bits.
    """
    img = Image.open(image_path).convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    pixels = np.asarray(img, dtype=np.float32)
    avg = pixels.mean()
    bits = (pixels > avg).flatten()
    return bits


def hamming_distance(bits_a, bits_b):
    return int(np.count_nonzero(bits_a != bits_b))


def detect_text_alignment(file_path, text=None):
    """
    Detect text layout alignment: Left, Right, Center, Justified.
    If PDF and PyMuPDF (fitz) is available, inspect text block bounding boxes.
    Otherwise analyze text indentation, spaces, and line structures.
    """
    ext = file_path.rsplit(".", 1)[1].lower() if "." in file_path else ""

    if ext == "pdf" and fitz:
        try:
            doc = fitz.open(file_path)
            center_count = 0
            left_count = 0
            right_count = 0
            justified_count = 0
            total_blocks = 0

            for page in doc:
                page_width = page.rect.width
                blocks = page.get_text("blocks")
                for b in blocks:
                    x0, y0, x1, y1, b_text, block_no, block_type = b[:7]
                    if not b_text.strip():
                        continue
                    total_blocks += 1
                    left_margin = x0
                    right_margin = page_width - x1
                    margin_diff = abs(left_margin - right_margin)

                    if margin_diff < 35 and left_margin > 40 and right_margin > 40:
                        center_count += 1
                    elif left_margin < right_margin - 30:
                        if abs(x1 - (page_width - left_margin)) < 15 and (x1 - x0) > (page_width * 0.6):
                            justified_count += 1
                        else:
                            left_count += 1
                    elif right_margin < left_margin - 30:
                        right_count += 1
                    else:
                        left_count += 1

            if total_blocks > 0:
                if center_count / total_blocks > 0.4:
                    return {"alignment": "Center", "confidence": round((center_count / total_blocks) * 100, 1), "details": "Detected via PDF block layout coordinates"}
                if right_count / total_blocks > 0.4:
                    return {"alignment": "Right", "confidence": round((right_count / total_blocks) * 100, 1), "details": "Detected via PDF block right margins"}
                if justified_count / total_blocks > 0.3:
                    return {"alignment": "Justified", "confidence": round((justified_count / total_blocks) * 100, 1), "details": "Detected via PDF block width & margins"}
                return {"alignment": "Left", "confidence": round((left_count / total_blocks) * 100, 1), "details": "Detected via standard left-margin PDF alignment"}
        except Exception:
            pass

    # Fallback to string analysis
    if not text:
        text = extract_text_from_file(file_path)

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {"alignment": "Left (Default)", "confidence": 100.0, "details": "No readable text content"}

    leading_spaces = [len(line) - len(line.lstrip(' ')) for line in lines]
    avg_leading = sum(leading_spaces) / len(leading_spaces)
    center_aligned_lines = 0
    right_aligned_lines = 0

    for line in lines:
        stripped = line.strip()
        leading = len(line) - len(line.lstrip(' '))
        trailing = len(line) - len(line.rstrip(' '))
        if leading > 10 and abs(leading - trailing) <= 4:
            center_aligned_lines += 1
        elif leading > 15 and trailing <= 3:
            right_aligned_lines += 1

    total = len(lines)
    if center_aligned_lines / total > 0.35:
        return {"alignment": "Center", "confidence": round((center_aligned_lines / total) * 100, 1), "details": "Indent pattern indicates centered text lines"}
    elif right_aligned_lines / total > 0.35:
        return {"alignment": "Right", "confidence": round((right_aligned_lines / total) * 100, 1), "details": "Indent pattern indicates right-aligned text lines"}
    elif avg_leading > 8:
        return {"alignment": "Indented / Custom", "confidence": 85.0, "details": "Consistently indented text formatting"}
    
    return {"alignment": "Left", "confidence": 95.0, "details": "Standard left-aligned text formatting"}


def word_wise_compare(text_a, text_b):
    words_a = re.findall(r'\b\w+\b', text_a.lower())
    words_b = re.findall(r'\b\w+\b', text_b.lower())

    set_a, set_b = set(words_a), set(words_b)
    common_words = set_a.intersection(set_b)
    all_words = set_a.union(set_b)

    jaccard_sim = (len(common_words) / len(all_words) * 100) if all_words else 0.0

    return {
        "word_count_a": len(words_a),
        "word_count_b": len(words_b),
        "unique_vocab_a": len(set_a),
        "unique_vocab_b": len(set_b),
        "common_words_count": len(common_words),
        "vocabulary_similarity_pct": round(jaccard_sim, 1),
        "sample_common_words": sorted(list(common_words))[:12]
    }


def sentence_wise_compare(text_a, text_b):
    sentences_a = [s.strip() for s in re.split(r'[.!?]+', text_a) if s.strip()]
    sentences_b = [s.strip() for s in re.split(r'[.!?]+', text_b) if s.strip()]

    set_s_a = set(sentences_a)
    set_s_b = set(sentences_b)
    common_sentences = set_s_a.intersection(set_s_b)

    match_pct = (len(common_sentences) * 2.0 / (len(sentences_a) + len(sentences_b)) * 100) if (sentences_a or sentences_b) else 0.0

    return {
        "sentence_count_a": len(sentences_a),
        "sentence_count_b": len(sentences_b),
        "matching_sentences_count": len(common_sentences),
        "sentence_similarity_pct": round(match_pct, 1),
    }


def line_and_page_wise_compare(path_a, path_b, text_a, text_b):
    lines_a = [l.strip() for l in text_a.splitlines() if l.strip()]
    lines_b = [l.strip() for l in text_b.splitlines() if l.strip()]

    matching_lines = len(set(lines_a).intersection(set(lines_b)))
    line_sim_pct = (matching_lines * 2.0 / (len(lines_a) + len(lines_b)) * 100) if (lines_a or lines_b) else 0.0

    pages_a, pages_b = 1, 1
    if path_a.lower().endswith(".pdf") and fitz:
        try:
            pages_a = len(fitz.open(path_a))
        except Exception:
            pass
    if path_b.lower().endswith(".pdf") and fitz:
        try:
            pages_b = len(fitz.open(path_b))
        except Exception:
            pass

    return {
        "line_count_a": len(lines_a),
        "line_count_b": len(lines_b),
        "matching_lines_count": matching_lines,
        "line_similarity_pct": round(line_sim_pct, 1),
        "page_count_a": pages_a,
        "page_count_b": pages_b,
        "page_match": pages_a == pages_b
    }


def compare_files(path_a, name_a, path_b, name_b):
    hash_a = compute_file_hash(path_a)
    hash_b = compute_file_hash(path_b)
    exact_match = hash_a == hash_b

    # Extract text content for granular comparisons
    text_a = extract_text_from_file(path_a)
    text_b = extract_text_from_file(path_b)

    alignment_a = detect_text_alignment(path_a, text_a)
    alignment_b = detect_text_alignment(path_b, text_b)

    word_metrics = word_wise_compare(text_a, text_b)
    sentence_metrics = sentence_wise_compare(text_a, text_b)
    line_page_metrics = line_and_page_wise_compare(path_a, path_b, text_a, text_b)

    result = {
        "hash_a": hash_a,
        "hash_b": hash_b,
        "exact_match": exact_match,
        "both_images": False,
        "similarity_pct": None,
        "perceptual_verdict": None,
        "alignment_a": alignment_a,
        "alignment_b": alignment_b,
        "word_metrics": word_metrics,
        "sentence_metrics": sentence_metrics,
        "line_page_metrics": line_page_metrics,
    }

    if exact_match:
        result["verdict"] = "IDENTICAL"
        result["summary"] = "These files are byte-for-byte identical."
        return result

    if is_image_file(name_a) and is_image_file(name_b):
        result["both_images"] = True
        try:
            bits_a = compute_average_hash(path_a)
            bits_b = compute_average_hash(path_b)
            distance = hamming_distance(bits_a, bits_b)
            max_distance = len(bits_a)
            similarity_pct = round((1 - distance / max_distance) * 100, 1)
            result["similarity_pct"] = similarity_pct
            result["hamming_distance"] = distance

            if similarity_pct >= 95:
                result["verdict"] = "NEAR_DUPLICATE"
                result["perceptual_verdict"] = "Very likely the same image (resized, recompressed, or lightly edited)"
                result["summary"] = f"Not byte-identical, but {similarity_pct}% visually similar - very likely the same image, possibly resaved or edited."
            elif similarity_pct >= 80:
                result["verdict"] = "SIMILAR"
                result["perceptual_verdict"] = "Noticeably similar - may share common origin or content"
                result["summary"] = f"{similarity_pct}% visually similar. These may be related images or share common source content."
            else:
                result["verdict"] = "DIFFERENT"
                result["perceptual_verdict"] = "Visually distinct"
                result["summary"] = f"Only {similarity_pct}% visually similar - these appear to be different images."
        except Exception as exc:
            result["verdict"] = "DIFFERENT"
            result["summary"] = f"Files are different (perceptual comparison failed: {exc})"
    else:
        # Check text similarity percentage if text is present
        vocab_sim = word_metrics.get("vocabulary_similarity_pct", 0)
        sentence_sim = sentence_metrics.get("sentence_similarity_pct", 0)
        avg_text_sim = (vocab_sim + sentence_sim) / 2.0

        if avg_text_sim >= 90:
            result["verdict"] = "HIGHLY_SIMILAR_TEXT"
            result["summary"] = f"Files have {round(avg_text_sim, 1)}% text overlap across sentences and vocabulary."
        elif avg_text_sim >= 50:
            result["verdict"] = "MODERATELY_SIMILAR_TEXT"
            result["summary"] = f"Files share {round(avg_text_sim, 1)}% content similarity."
        else:
            result["verdict"] = "DIFFERENT"
            result["summary"] = "These files are different in binary hash and text content."

    return result

