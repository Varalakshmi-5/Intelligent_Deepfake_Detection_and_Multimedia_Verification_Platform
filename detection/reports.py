from fpdf import FPDF
from datetime import datetime, timezone


def sanitize_pdf_text(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "—": "-", "–": "-", "…": "...", "•": "-",
        "™": "(TM)", "®": "(R)", "©": "(C)",
        "\u200b": "", "\xa0": " "
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class ReportPDF(FPDF):
    def normalize_text(self, txt):
        txt = sanitize_pdf_text(txt)
        return super().normalize_text(txt)

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(20, 30, 40)
        self.cell(0, 10, "Deepfake Verification Report", ln=True, align="C")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, "AI-Powered Multimedia Authenticity Platform", ln=True, align="C")
        self.ln(4)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        from django.utils import timezone as django_tz
        self.cell(0, 10, f"Generated on {django_tz.now().strftime('%Y-%m-%d %H:%M IST')}", align="C")


def build_image_report(output_path, data, image_path=None, ela_path=None, gradcam_path=None):
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    is_real = data["prediction"] == "REAL"
    if is_real:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)
    else:
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RESULT: {data['prediction']}  (confidence {data['confidence']}%)", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if image_path:
        try:
            pdf.image(image_path, x=75, w=60)
            pdf.set_xy(pdf.l_margin, pdf.get_y() + 4)
        except Exception:
            pass

    section_title("Image Information")
    kv_row("Filename:", data.get("filename", "-"))
    kv_row("Format:", data.get("format", "-"))
    kv_row("Color Mode:", data.get("mode", "-"))
    kv_row("Dimensions:", f"{data.get('width', '-')} x {data.get('height', '-')} px")
    kv_row("File Size:", f"{data.get('file_size_kb', '-')} KB")
    pdf.ln(2)

    section_title("AI Model Analysis")
    kv_row("Model:", data.get("model_name", "-"))
    kv_row("Test Accuracy:", data.get("model_accuracy", "-"))
    kv_row("ROC-AUC:", data.get("model_roc_auc", "-"))
    kv_row("Raw Probability (REAL):", data.get("probability", "-"))
    kv_row("Prediction:", data["prediction"])
    kv_row("Confidence:", f"{data['confidence']}%")
    pdf.ln(2)

    section_title("Forensic Analysis")
    kv_row("ELA Irregularity Score:", f"{data.get('ela_irregularity_score', '-')} / 100")
    kv_row("Grad-CAM Focus Area:", f"{data.get('gradcam_focus_pct', '-')}% of image")

    if ela_path or gradcam_path:
        pdf.ln(3)
        y_before = pdf.get_y()
        if ela_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(20, y_before, "Error Level Analysis")
            try:
                pdf.image(ela_path, x=15, y=y_before + 2, w=80)
            except Exception:
                pass
        if gradcam_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(115, y_before, "Grad-CAM Attention Map")
            try:
                pdf.image(gradcam_path, x=110, y=y_before + 2, w=80)
            except Exception:
                pass
        pdf.set_xy(pdf.l_margin, y_before + 65)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_video_report(output_path, data, frame_path=None, ela_path=None, gradcam_path=None):
    """
    data: dict with keys - filename, user_name, user_email, prediction,
          confidence, fake_probability, real_probability, threshold,
          duration_sec, fps, width, height, file_size_mb, total_frames,
          faces_detected, model_name,
          ela_irregularity_score, gradcam_focus_pct,
          average_brightness, brightness_std, average_sharpness,
          sharpness_std, average_noise, noise_std, average_frame_difference,
          analyzed_at
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    is_real = data["prediction"] == "REAL"
    if is_real:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)
    else:
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RESULT: {data['prediction']}  (confidence {data['confidence']}%)", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if frame_path:
        try:
            pdf.image(frame_path, x=75, w=60)
            pdf.set_xy(pdf.l_margin, pdf.get_y() + 4)
        except Exception:
            pass

    section_title("Video Information")
    kv_row("Filename:", data.get("filename", "-"))
    kv_row("Duration:", f"{data.get('duration_sec', '-')} sec")
    kv_row("FPS:", data.get("fps", "-"))
    kv_row("Resolution:", f"{data.get('width', '-')} x {data.get('height', '-')} px")
    kv_row("Total Frames:", data.get("total_frames", "-"))
    kv_row("File Size:", f"{data.get('file_size_mb', '-')} MB")
    kv_row("Faces Detected (sample frame):", data.get("faces_detected", "-"))
    pdf.ln(2)

    section_title("AI Model Analysis")
    kv_row("Model:", data.get("model_name", "-"))
    kv_row("Prediction:", data["prediction"])
    kv_row("Confidence:", f"{data['confidence']}%")
    kv_row("Real Probability:", f"{round(data.get('real_probability', 0) * 100, 2)}%")
    kv_row("Fake Probability:", f"{round(data.get('fake_probability', 0) * 100, 2)}%")
    kv_row("Decision Threshold:", f"{data.get('threshold', '-')} (fake probability)")
    pdf.ln(2)

    section_title("Multi-Frame Forensic Consistency")
    kv_row("Frames Analyzed:", data.get("frames_analyzed", "-"))
    kv_row("Avg Brightness (Std):", f"{data.get('average_brightness', '-')} ({data.get('brightness_std', '-')})")
    kv_row("Avg Sharpness (Std):", f"{data.get('average_sharpness', '-')} ({data.get('sharpness_std', '-')})")
    kv_row("Avg Noise (Std):", f"{data.get('average_noise', '-')} ({data.get('noise_std', '-')})")
    kv_row("Avg Frame Difference:", data.get("average_frame_difference", "-"))
    pdf.ln(2)

    section_title("Image-Level Forensic Analysis (Sample Frame)")
    kv_row("ELA Irregularity Score:", f"{data.get('ela_irregularity_score', '-')} / 100")
    kv_row("Grad-CAM Focus Area:", f"{data.get('gradcam_focus_pct', '-')}% of frame")

    if ela_path or gradcam_path:
        pdf.ln(3)
        y_before = pdf.get_y()
        if ela_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(20, y_before, "Error Level Analysis")
            try:
                pdf.image(ela_path, x=15, y=y_before + 2, w=80)
            except Exception:
                pass
        if gradcam_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(115, y_before, "Grad-CAM Attention Map")
            try:
                pdf.image(gradcam_path, x=110, y=y_before + 2, w=80)
            except Exception:
                pass
        pdf.set_xy(pdf.l_margin, y_before + 65)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_audio_report(output_path, data, spectrogram_path=None, waveform_path=None, gradcam_path=None):
    """
    data: dict with keys - filename, user_name, user_email, prediction,
          confidence, real_probability, fake_probability,
          duration_sec, sample_rate, channels, subtype, file_size_kb,
          model_name, model_accuracy, model_roc_auc, gradcam_focus_pct,
          analyzed_at
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    is_real = data["prediction"] == "REAL"
    if is_real:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)
    else:
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RESULT: {data['prediction']}  (confidence {data['confidence']}%)", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    section_title("Audio Information")
    kv_row("Filename:", data.get("filename", "-"))
    kv_row("Format:", data.get("format", "-"))
    kv_row("Duration:", f"{data.get('duration_sec', '-')} sec")
    kv_row("Sample Rate:", f"{data.get('sample_rate', '-')} Hz")
    kv_row("Channels:", data.get("channels", "-"))
    kv_row("Subtype:", data.get("subtype", "-"))
    kv_row("File Size:", f"{data.get('file_size_kb', '-')} KB")
    pdf.ln(2)

    section_title("AI Model Analysis")
    kv_row("Model:", data.get("model_name", "-"))
    kv_row("Test Accuracy:", data.get("model_accuracy", "-"))
    kv_row("ROC-AUC:", data.get("model_roc_auc", "-"))
    kv_row("Prediction:", data["prediction"])
    kv_row("Confidence:", f"{data['confidence']}%")
    kv_row("Real Probability:", f"{round(data.get('real_probability', 0) * 100, 2)}%")
    kv_row("Fake Probability:", f"{round(data.get('fake_probability', 0) * 100, 2)}%")
    pdf.ln(2)

    section_title("Forensic Analysis")
    kv_row("Grad-CAM Focus Area:", f"{data.get('gradcam_focus_pct', '-')}% of spectrogram")

    if waveform_path:
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 6, "Waveform", new_x="LMARGIN", new_y="NEXT")
        try:
            pdf.image(waveform_path, x=pdf.l_margin, w=180)
            pdf.ln(3)
        except Exception:
            pass

    if spectrogram_path or gradcam_path:
        y_before = pdf.get_y()
        if spectrogram_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(20, y_before, "Log-Mel Spectrogram")
            try:
                pdf.image(spectrogram_path, x=15, y=y_before + 2, w=80)
            except Exception:
                pass
        if gradcam_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(115, y_before, "Grad-CAM Attention Map")
            try:
                pdf.image(gradcam_path, x=110, y=y_before + 2, w=80)
            except Exception:
                pass
        pdf.set_xy(pdf.l_margin, y_before + 48)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_text_report(output_path, data, human_words=None, ai_words=None):
    """
    data: dict with keys - excerpt, user_name, user_email, prediction,
          prediction_label, confidence, real_probability, fake_probability,
          verdict, character_count, word_count, sentence_count,
          average_word_length, average_sentence_length, unique_words,
          vocabulary_richness, uppercase_count, digit_count,
          punctuation_count, model_name, model_accuracy, model_roc_auc,
          analyzed_at
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    is_real = data["prediction"] == "REAL"
    if is_real:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)
    else:
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RESULT: {data['prediction_label']}  (confidence {data['confidence']}%)", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    section_title("Analyzed Text (excerpt)")
    pdf.set_font("Helvetica", "I", 9.5)
    pdf.set_text_color(60, 60, 60)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, data.get("excerpt", "-"))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    section_title("Text Statistics")
    kv_row("Character Count:", data.get("character_count", "-"))
    kv_row("Word Count:", data.get("word_count", "-"))
    kv_row("Sentence Count:", data.get("sentence_count", "-"))
    kv_row("Avg Word Length:", data.get("average_word_length", "-"))
    kv_row("Avg Sentence Length:", data.get("average_sentence_length", "-"))
    kv_row("Unique Words:", data.get("unique_words", "-"))
    kv_row("Vocabulary Richness:", data.get("vocabulary_richness", "-"))
    kv_row("Uppercase Characters:", data.get("uppercase_count", "-"))
    kv_row("Digits:", data.get("digit_count", "-"))
    kv_row("Punctuation:", data.get("punctuation_count", "-"))
    pdf.ln(2)

    section_title("AI Model Analysis")
    kv_row("Model:", data.get("model_name", "-"))
    kv_row("Test Accuracy:", data.get("model_accuracy", "-"))
    kv_row("ROC-AUC:", data.get("model_roc_auc", "-"))
    kv_row("Prediction:", data.get("prediction_label", "-"))
    kv_row("Verdict:", data.get("verdict", "-"))
    kv_row("Confidence:", f"{data['confidence']}%")
    kv_row("Human/Real Probability:", f"{round(data.get('real_probability', 0) * 100, 2)}%")
    kv_row("AI/Fake Probability:", f"{round(data.get('fake_probability', 0) * 100, 2)}%")
    pdf.ln(2)

    if human_words or ai_words:
        section_title("Linguistic Interpretability")
        pdf.set_font("Helvetica", "", 10)
        if human_words:
            pdf.set_x(pdf.l_margin)
            pdf.set_text_color(15, 120, 60)
            terms = ", ".join(w["term"] for w in human_words)
            pdf.multi_cell(0, 6, f"Human-indicative terms: {terms}")
        if ai_words:
            pdf.set_x(pdf.l_margin)
            pdf.set_text_color(180, 30, 30)
            terms = ", ".join(w["term"] for w in ai_words)
            pdf.multi_cell(0, 6, f"AI-indicative terms: {terms}")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_document_report(output_path, data, page_images=None):
    """
    data: dict with keys - filename, user_name, user_email, file_type,
          risk_tier, verdict, risk_points, flags (list of str),
          page_count, pdf_meta (dict or None), ocr_text_preview,
          analyzed_at
    page_images: list of (label, image_path) tuples to embed, e.g.
                 [("Page 1 - ELA", path), ("Page 1 - Copy-Move", path)]
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    tier = data.get("risk_tier", "LOW")
    if tier == "HIGH":
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)
    elif tier == "MEDIUM":
        pdf.set_fill_color(255, 240, 214)
        pdf.set_text_color(180, 120, 10)
    else:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RISK LEVEL: {tier}  -  {data.get('verdict', '-')}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, "This is a rule-based forensic assessment, not an AI confidence score. "
                         "Each flag below is a deterministic, explainable signal. Treat results as "
                         "leads for further review, not definitive proof of forgery.")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    section_title("Document Information")
    kv_row("Filename:", data.get("filename", "-"))
    kv_row("File Type:", data.get("file_type", "-"))
    kv_row("Pages Analyzed:", data.get("page_count", "-"))
    pdf.ln(2)

    if data.get("pdf_meta"):
        meta = data["pdf_meta"]
        section_title("PDF Metadata & Revision Forensics")
        kv_row("Creation Date:", meta.get("creation_date", "-"))
        kv_row("Modification Date:", meta.get("modification_date", "-"))
        kv_row("Producer:", meta.get("producer", "-"))
        kv_row("Creator:", meta.get("creator", "-"))
        kv_row("Incremental Updates:", meta.get("incremental_updates", "-"))
        kv_row("Digital Signature Present:", "Yes" if meta.get("has_digital_signature") else "No")
        kv_row("File Size:", f"{meta.get('file_size_kb', '-')} KB")
        pdf.ln(2)

    section_title("Findings")
    for flag in data.get("flags", []):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 6.5, f"-  {flag}")
    pdf.ln(2)

    if data.get("ocr_text_preview"):
        section_title("Extracted Text (preview)")
        pdf.set_font("Helvetica", "I", 9.5)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, data["ocr_text_preview"])
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    if page_images:
        for label, img_path in page_images:
            if pdf.get_y() > 180:
                pdf.add_page()
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_x(pdf.l_margin)
            pdf.cell(0, 6, label, new_x="LMARGIN", new_y="NEXT")
            try:
                pdf.image(img_path, x=pdf.l_margin, w=110)
                pdf.ln(3)
            except Exception:
                pass

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_link_report(output_path, data):
    """
    data: filename(url), user_name, user_email, risk_tier, verdict,
          risk_points, flags, host, analyzed_at
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    tier = data.get("risk_tier", "LOW")
    if tier == "HIGH":
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)
    elif tier == "MEDIUM":
        pdf.set_fill_color(255, 240, 214)
        pdf.set_text_color(180, 120, 10)
    else:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RISK LEVEL: {tier}  -  {data.get('verdict', '-')}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    section_title("URL Analyzed")
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6.5, data.get("filename", "-"))
    pdf.ln(2)

    kv_row("Host:", data.get("host", "-"))
    pdf.ln(2)

    section_title("Findings")
    for flag in data.get("flags", []):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 10.5)
        pdf.multi_cell(0, 6.5, f"-  {flag}")
    pdf.ln(2)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_compare_report(output_path, data, image_a_path=None, image_b_path=None):
    """
    data: file_a_name, file_b_name, verdict, summary, hash_a, hash_b,
          exact_match, similarity_pct, user_name, user_email, analyzed_at
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(55, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    verdict = data.get("verdict", "DIFFERENT")
    if verdict == "IDENTICAL":
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)
    elif verdict in ("NEAR_DUPLICATE", "SIMILAR"):
        pdf.set_fill_color(255, 240, 214)
        pdf.set_text_color(180, 120, 10)
    else:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  RESULT: {verdict.replace('_', ' ')}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "I", 10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, data.get("summary", "-"))
    pdf.ln(3)

    if image_a_path or image_b_path:
        y_before = pdf.get_y()
        if image_a_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(20, y_before, "File A")
            try:
                pdf.image(image_a_path, x=15, y=y_before + 2, w=80)
            except Exception:
                pass
        if image_b_path:
            pdf.set_font("Helvetica", "I", 9)
            pdf.text(115, y_before, "File B")
            try:
                pdf.image(image_b_path, x=110, y=y_before + 2, w=80)
            except Exception:
                pass
        pdf.set_xy(pdf.l_margin, y_before + 65)

    section_title("File Details")
    kv_row("File A:", data.get("file_a_name", "-"))
    kv_row("File B:", data.get("file_b_name", "-"))
    kv_row("SHA-256 A:", data.get("hash_a", "-"))
    kv_row("SHA-256 B:", data.get("hash_b", "-"))
    kv_row("Exact Match:", "Yes" if data.get("exact_match") else "No")
    if data.get("similarity_pct") is not None:
        kv_row("Visual Similarity:", f"{data['similarity_pct']}%")
    pdf.ln(2)

    align_a = data.get("alignment_a")
    align_b = data.get("alignment_b")
    if align_a or align_b:
        section_title("Layout & Text Alignment Analysis")
        if align_a:
            kv_row("File A Alignment:", f"{align_a.get('alignment', '-')} ({align_a.get('confidence', 0)}% confidence)")
        if align_b:
            kv_row("File B Alignment:", f"{align_b.get('alignment', '-')} ({align_b.get('confidence', 0)}% confidence)")
        pdf.ln(2)

    word_m = data.get("word_metrics")
    sent_m = data.get("sentence_metrics")
    lp_m = data.get("line_page_metrics")

    if word_m or sent_m or lp_m:
        section_title("Granular Feature Breakdown")
        if word_m:
            kv_row("Word-wise Similarity:", f"{word_m.get('vocabulary_similarity_pct', 0)}% (File A: {word_m.get('word_count_a', 0)} words, File B: {word_m.get('word_count_b', 0)} words)")
        if sent_m:
            kv_row("Sentence-wise Match:", f"{sent_m.get('sentence_similarity_pct', 0)}% ({sent_m.get('matching_sentences_count', 0)} matching sentences)")
        if lp_m:
            kv_row("Line-wise Match:", f"{lp_m.get('line_similarity_pct', 0)}% ({lp_m.get('matching_lines_count', 0)} matching lines)")
            kv_row("Page-wise Match:", f"{'Matches' if lp_m.get('page_match') else 'Differs'} (File A: {lp_m.get('page_count_a', 1)} pages, File B: {lp_m.get('page_count_b', 1)} pages)")
        pdf.ln(2)

    section_title("Verification Details")
    kv_row("Analyzed By:", f"{data.get('user_name', '-')} ({data.get('user_email', '-')})")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))

    pdf.output(output_path)
    return output_path


def build_proctor_report(output_path, data, snapshot_path=None):
    """
    data: dict with session_id, user_name, user_email, integrity_score, verdict,
          violations_count, warnings (list), allowed_objects (list), analyzed_at
    snapshot_path: path to camera snapshot image if captured
    """
    pdf = ReportPDF()
    pdf.add_page()

    def section_title(text):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 30, 40)
        pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)

    def kv_row(label, value):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(60, 7, str(label), border=0, new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        value_text = str(value) if value not in (None, "") else "-"
        pdf.multi_cell(0, 7, value_text, new_x="LMARGIN", new_y="NEXT")

    score = data.get("integrity_score", 100)
    if score >= 85:
        pdf.set_fill_color(224, 247, 233)
        pdf.set_text_color(15, 120, 60)
        verdict_str = "CLEAN & VERIFIED"
    elif score >= 50:
        pdf.set_fill_color(255, 240, 214)
        pdf.set_text_color(180, 120, 10)
        verdict_str = "MODERATE WARNINGS"
    else:
        pdf.set_fill_color(253, 226, 226)
        pdf.set_text_color(180, 30, 30)
        verdict_str = "HIGH RISK / PROHIBITED ITEMS"

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 14, f"  INTEGRITY SCORE: {score}%  -  {verdict_str}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if snapshot_path and os.path.exists(snapshot_path):
        try:
            pdf.image(snapshot_path, x=55, w=100)
            pdf.ln(4)
        except Exception:
            pass

    section_title("Session Overview")
    kv_row("Candidate Name:", data.get("user_name", "-"))
    kv_row("Candidate Email:", data.get("user_email", "-"))
    kv_row("Proctoring Session ID:", data.get("session_id", "-"))
    kv_row("Environment Integrity:", f"{score}%")
    kv_row("Prohibited Objects Found:", data.get("violations_count", 0))
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))
    pdf.ln(2)

    warnings = data.get("warnings", [])
    if warnings:
        section_title("Flagged Environment Warnings")
        for w in warnings:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(180, 30, 30)
            msg = w.get("message") if isinstance(w, dict) else str(w)
            clean_msg = msg.replace("⚠️", "[WARNING]").replace("•", "-").encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 6, f"- {clean_msg}")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    pdf.output(output_path)
    return output_path



