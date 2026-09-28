"""
Generates a UPI payment QR code as a base64 data URI for inline embedding
in templates — no file storage needed since the amount/payee are static
config, not per-user.
"""
import base64
import io
import urllib.parse

import qrcode
from django.conf import settings


def build_upi_uri(amount_inr, payee_vpa, payee_name, note=""):
    params = {
        "pa": payee_vpa,
        "pn": payee_name,
        "am": str(amount_inr),
        "cu": "INR",
    }
    if note:
        params["tn"] = note
    query = urllib.parse.urlencode(params)
    return f"upi://pay?{query}"


def generate_upi_qr_data_uri(amount_inr=None, note=""):
    """Returns a data:image/png;base64,... string ready for an <img src="">."""
    amount_inr = amount_inr or settings.PAID_ACCESS_PRICE_INR
    uri = build_upi_uri(amount_inr, settings.UPI_ID, settings.UPI_PAYEE_NAME, note=note)

    img = qrcode.make(uri, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
