"""
Verified Authenticity Certificate: a one-page, shareable PDF for content
that came back authentic, with a QR code linking to a public (no-login)
verification page. The public page deliberately shows minimal
information (verdict, hash, date) — never the uploader's identity or
the actual file content — so the link is safe to share without exposing
anything private about the person who ran the check.
"""
import hashlib
import qrcode
from fpdf import FPDF


def compute_file_hash(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_qr_code(url, output_path):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)




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


class CertificatePDF(FPDF):
    def normalize_text(self, txt):
        txt = sanitize_pdf_text(txt)
        return super().normalize_text(txt)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, "This certificate can be independently re-verified online using the link above.", align="C")


def build_certificate_pdf(output_path, data, qr_path=None):
    """
    data: dict with keys - filename, media_type, file_hash, verdict_label,
          confidence, analyzed_at, user_name, public_id, verify_url
    """
    pdf = CertificatePDF(format="A4")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(20, 30, 40)
    pdf.ln(10)
    pdf.cell(0, 14, "Verified Authenticity Certificate", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 8, "AI-Powered Multimedia Authenticity Platform", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_draw_color(62, 230, 208)
    pdf.set_line_width(1)
    pdf.line(30, pdf.get_y(), 180, pdf.get_y())
    pdf.ln(10)

    # Verdict badge
    pdf.set_fill_color(224, 247, 233)
    pdf.set_text_color(15, 120, 60)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 16, f"  {data.get('verdict_label', 'VERIFIED AUTHENTIC')}", align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # Verification URL Box
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(70, 70, 70)
    pdf.cell(0, 6, "Digital Certificate Verification Link:", align="C", new_x="LMARGIN", new_y="NEXT")
    
    verify_url = data.get("verify_url", "")
    if verify_url:
        pdf.set_font("Helvetica", "U", 10)
        pdf.set_text_color(37, 99, 235)
        pdf.cell(0, 8, verify_url, align="C", link=verify_url, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(12)



    def kv_row(label, value):
        pdf.set_x(40)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(70, 70, 70)
        pdf.cell(45, 8, str(label), border=0)
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 8, str(value) if value else "-")

    kv_row("File:", data.get("filename", "-"))
    kv_row("Media Type:", data.get("media_type", "-").title())
    kv_row("SHA-256 Hash:", data.get("file_hash", "-"))
    kv_row("Confidence:", f"{data.get('confidence', '-')}%")
    kv_row("Analyzed At:", data.get("analyzed_at", "-"))
    kv_row("Certificate ID:", str(data.get("public_id", "-")))

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(130, 130, 130)
    pdf.set_x(30)
    pdf.multi_cell(140, 5,
        "This certificate reflects an automated analysis at the time shown above and is not a "
        "legal guarantee of authenticity. The SHA-256 hash lets anyone confirm this certificate "
        "corresponds to a specific, unmodified file.", align="C")

    pdf.output(output_path)
    return output_path
