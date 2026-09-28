"""
Document forgery/tampering analysis — deliberately NOT a trained classifier.

This is a rule-based forensic pipeline (the same category of technique
real document-forensics tools use), because there is no readily available
pretrained model for document forgery detection, and a from-scratch model
needs labeled forgery data this project doesn't have. Every signal here is
deterministic and explainable — no confidence score is invented.

Checks:
  1. PDF metadata & revision forensics (creation/mod dates, producer,
     incremental-update count, digital signature presence)
  2. Error Level Analysis (reused from the image pipeline) on each
     rendered page
  3. Copy-move forgery detection (ORB keypoints clustered by translation
     vector, filtered for spatial compactness AND scaled cluster-size
     requirements to avoid false positives on legitimate repetitive
     layout elements like table grids or repeated text characters)
  4. OCR text extraction (pytesseract) for scanned/image-based pages
"""
import os
import numpy as np
import cv2
import fitz  # PyMuPDF
from PIL import Image
from collections import defaultdict

# Configure Tesseract OCR binary path for Document Analysis
possible_tesseract_dirs = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
]

for t_dir in possible_tesseract_dirs:
    if os.path.exists(t_dir):
        if t_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] += os.pathsep + t_dir
        t_exe = os.path.join(t_dir, "tesseract.exe")
        if os.path.exists(t_exe):
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = t_exe
            except Exception:
                pass
        break

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        TESSERACT_AVAILABLE = False
except ImportError:
    TESSERACT_AVAILABLE = False



from .forensics import generate_ela_image

MAX_PAGES_ANALYZED = 5
RENDER_DPI = 150


# ----------------------------------------------------------------
# File type detection
# ----------------------------------------------------------------

def is_pdf(filepath):
    with open(filepath, "rb") as f:
        header = f.read(5)
    return header == b"%PDF-"


# ----------------------------------------------------------------
# PDF metadata & revision forensics
# ----------------------------------------------------------------

def analyze_pdf_metadata(filepath):
    with open(filepath, "rb") as f:
        raw = f.read()

    eof_count = raw.count(b"%%EOF")
    incremental_updates = max(eof_count - 1, 0)

    has_signature = b"/ByteRange" in raw and (b"/Type/Sig" in raw or b"/Type /Sig" in raw)

    doc = fitz.open(filepath)
    metadata = doc.metadata or {}
    page_count = doc.page_count
    doc.close()

    creation_date = metadata.get("creationDate", "") or ""
    mod_date = metadata.get("modDate", "") or ""
    producer = metadata.get("producer", "") or ""
    creator = metadata.get("creator", "") or ""

    suspicious_producer_keywords = ["photoshop", "gimp", "paint.net", "illustrator"]
    producer_flag = any(
        kw in (producer + creator).lower() for kw in suspicious_producer_keywords
    )

    dates_differ = bool(creation_date and mod_date and creation_date != mod_date)

    return {
        "page_count": page_count,
        "creation_date": creation_date or "Not present",
        "modification_date": mod_date or "Not present",
        "producer": producer or "Not present",
        "creator": creator or "Not present",
        "incremental_updates": incremental_updates,
        "has_digital_signature": has_signature,
        "producer_flag": producer_flag,
        "dates_differ": dates_differ,
        "file_size_kb": round(os.path.getsize(filepath) / 1024, 2),
    }


# ----------------------------------------------------------------
# Page rendering (PDF -> images) + native text extraction
# ----------------------------------------------------------------

def render_pdf_pages(filepath, max_pages=MAX_PAGES_ANALYZED, dpi=RENDER_DPI):
    """Returns a list of (PIL.Image, native_text) tuples, one per analyzed page."""
    doc = fitz.open(filepath)
    pages = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    for i in range(min(doc.page_count, max_pages)):
        page = doc[i]
        native_text = page.get_text().strip()
        pixmap = page.get_pixmap(matrix=matrix)
        img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        pages.append((img, native_text))

    doc.close()
    return pages


def load_image_as_page(filepath):
    """For standalone document images (not PDFs): treat as a single page."""
    img = Image.open(filepath).convert("RGB")
    return [(img, "")]


# ----------------------------------------------------------------
# OCR
# ----------------------------------------------------------------

def ocr_page(pil_image):
    if not TESSERACT_AVAILABLE:
        return ""
    try:
        return pytesseract.image_to_string(pil_image).strip()
    except Exception as exc:
        print(f"[DOCUMENT OCR ERROR] {exc}")
        return ""


# ----------------------------------------------------------------
# Error Level Analysis (reused technique, per page)
# ----------------------------------------------------------------

def run_ela_on_page(pil_image, output_path):
    tmp_input = output_path + ".src.jpg"
    pil_image.save(tmp_input, "JPEG", quality=95)
    info = generate_ela_image(tmp_input, output_path)
    os.remove(tmp_input)
    return info


# ----------------------------------------------------------------
# Copy-move forgery detection
# ----------------------------------------------------------------

def detect_copy_move(pil_image, output_path, min_distance=60, bin_size=6,
                      min_cluster_size=30, min_cluster_fraction=0.035, max_bbox_fraction=0.30,
                      max_hamming_distance=25):
    """
    Detects copy-pasted regions WITHIN the same page image using ORB
    keypoint matching, clustered by translation vector. A genuine
    copy-paste forgery produces many keypoint pairs sharing nearly the
    same offset AND both the source and destination points stay within a
    compact area (a stamp, signature, or photo) — unlike legitimate
    repetitive layout elements (table grids, letterhead rules) or
    repeated text characters/glyphs, which either scatter across the
    whole page or don't form a large-enough consistent cluster, and get
    filtered out here. The cluster-size requirement scales with the
    total keypoint count so dense, text-heavy pages need proportionally
    more matching points before being flagged, not just a fixed count.
    """
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=3000)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    if descriptors is None or len(keypoints) < 10:
        cv2.imwrite(output_path, img)
        return {"suspicious": False, "cluster_size": 0, "keypoints_found": len(keypoints) if keypoints else 0}

    required_cluster_size = max(min_cluster_size, int(len(keypoints) * min_cluster_fraction))

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(descriptors, descriptors, k=6)

    offset_groups = defaultdict(list)
    seen_pairs = set()

    for match_group in matches:
        for m in match_group:
            if m.queryIdx == m.trainIdx or m.distance > max_hamming_distance:
                continue
            pair_key = tuple(sorted([m.queryIdx, m.trainIdx]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            pt1 = np.array(keypoints[m.queryIdx].pt)
            pt2 = np.array(keypoints[m.trainIdx].pt)
            if np.linalg.norm(pt1 - pt2) < min_distance:
                continue

            dx, dy = pt2 - pt1
            offset_key = (round(dx / bin_size) * bin_size, round(dy / bin_size) * bin_size)
            offset_groups[offset_key].append((pt1, pt2))

    candidates = sorted(offset_groups.items(), key=lambda kv: len(kv[1]), reverse=True)

    best = None
    for offset_key, group in candidates:
        if len(group) < required_cluster_size:
            break
        src_pts = np.array([p[0] for p in group])
        dst_pts = np.array([p[1] for p in group])
        src_bbox = (src_pts[:, 0].max() - src_pts[:, 0].min(), src_pts[:, 1].max() - src_pts[:, 1].min())
        dst_bbox = (dst_pts[:, 0].max() - dst_pts[:, 0].min(), dst_pts[:, 1].max() - dst_pts[:, 1].min())
        if (src_bbox[0] < w * max_bbox_fraction and src_bbox[1] < h * max_bbox_fraction and
                dst_bbox[0] < w * max_bbox_fraction and dst_bbox[1] < h * max_bbox_fraction):
            best = (offset_key, group)
            break

    if best is None:
        cv2.imwrite(output_path, img)
        return {"suspicious": False, "cluster_size": 0, "keypoints_found": len(keypoints)}

    offset_key, group = best
    result_img = img.copy()
    for pt1, pt2 in group:
        p1, p2 = tuple(pt1.astype(int)), tuple(pt2.astype(int))
        cv2.line(result_img, p1, p2, (0, 0, 255), 1)
        cv2.circle(result_img, p1, 4, (0, 255, 255), -1)
        cv2.circle(result_img, p2, 4, (0, 255, 255), -1)
    cv2.imwrite(output_path, result_img)

    return {"suspicious": True, "cluster_size": len(group), "keypoints_found": len(keypoints)}


# ----------------------------------------------------------------
# Overall risk scoring (explainable, not a black-box confidence number)
# ----------------------------------------------------------------

def compute_risk_assessment(pdf_meta, ela_scores, copy_move_results):
    """
    Combines every signal into a small set of explicit flags plus a risk
    tier. Deliberately not framed as a percentage confidence — that would
    imply a precision this rule-based approach doesn't have.
    """
    flags = []
    points = 0

    if pdf_meta is not None:
        if pdf_meta["incremental_updates"] >= 4:
            flags.append(f"PDF has been saved {pdf_meta['incremental_updates']} times after initial creation (high revision count)")
            points += 3
        elif pdf_meta["incremental_updates"] >= 2:
            flags.append(f"PDF has {pdf_meta['incremental_updates']} incremental updates after initial creation")
            points += 1

        if pdf_meta["producer_flag"]:
            flags.append(f"Produced/edited with image-editing software ({pdf_meta['producer'] or pdf_meta['creator']})")
            points += 2

        if pdf_meta["dates_differ"]:
            points += 0  # informational only, too common to be a strong signal on its own

    max_ela = max(ela_scores) if ela_scores else 0
    if max_ela > 55:
        flags.append(f"High Error Level Analysis irregularity detected (score {round(max_ela, 1)}/100)")
        points += 3
    elif max_ela > 35:
        flags.append(f"Moderate Error Level Analysis irregularity detected (score {round(max_ela, 1)}/100)")
        points += 1

    any_copy_move = any(r["suspicious"] for r in copy_move_results)
    if any_copy_move:
        best = max(copy_move_results, key=lambda r: r.get("cluster_size", 0))
        flags.append(f"Duplicated region detected within the document (copy-move pattern, {best['cluster_size']} matched points)")
        points += 3

    if points >= 6:
        tier = "HIGH"
        verdict = "Multiple Irregularities Found"
    elif points >= 3:
        tier = "MEDIUM"
        verdict = "Some Irregularities Found"
    else:
        tier = "LOW"
        verdict = "No Significant Irregularities Found"

    if not flags:
        flags.append("No tampering indicators detected by any check")

    return {"risk_tier": tier, "verdict": verdict, "risk_points": points, "flags": flags}
