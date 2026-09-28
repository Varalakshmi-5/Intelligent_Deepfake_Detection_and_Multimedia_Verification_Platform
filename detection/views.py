import os
import uuid
import cv2
from datetime import datetime, timezone as dt_timezone
from django.utils import timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods


from .models import Detection, JobSearchQuery, JobListingVerification, RecruiterQuery, RecruiterVerification
from .job_verifier import search_and_verify_jobs, verify_recruiter_profile
from .ml import predict_image
from .forensics import generate_ela_image, generate_gradcam
from .reports import build_image_report, build_video_report, build_audio_report, build_text_report, build_document_report, build_link_report, build_compare_report, build_proctor_report
from .video_ml import (
    get_video_metadata, extract_middle_frame, preprocess_frame,
    predict_frame, detect_faces,
)
from .video_forensics import (
    forensic_video_analysis,
    generate_ela_image as generate_video_ela_image,
    generate_video_gradcam,
)
from .audio_ml import audio_to_spectrogram, predict_audio, get_audio_metadata, load_waveform
from .audio_forensics import generate_waveform_image, generate_spectrogram_image, generate_audio_gradcam
from .text_ml import analyze_text_metadata, predict_text, get_top_contributing_words
from .document_forensics import (
    is_pdf, analyze_pdf_metadata, render_pdf_pages, load_image_as_page,
    ocr_page, run_ela_on_page, detect_copy_move as detect_document_copy_move,
    compute_risk_assessment, TESSERACT_AVAILABLE,
)
from .certificate import compute_file_hash, compute_text_hash, generate_qr_code, build_certificate_pdf
from .link_checker import analyze_url
from .file_compare import compare_files, is_image_file
from billing.decorators import requires_detection_access

ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png"}


def _admin_redirect_if_needed(user):
    if user.is_admin:
        from django.shortcuts import redirect as _r
        return _r("adminpanel:dashboard")
    return None


@login_required
def dashboard(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    my_detections = Detection.objects.filter(user=request.user).order_by("-created_at")
    total_count = my_detections.count()
    fake_count = my_detections.filter(result="FAKE").count()
    real_count = my_detections.filter(result="REAL").count()
    unverified_count = max(0, total_count - (real_count + fake_count))
    recent = my_detections[:5]

    from django.db.models import Count
    media_breakdown = my_detections.values("media_type").annotate(count=Count("id")).order_by("-count")
    user_media_labels = [m["media_type"].capitalize() for m in media_breakdown]
    user_media_data = [m["count"] for m in media_breakdown]

    return render(request, "detection/dashboard.html", {
        "user": request.user,
        "active_nav": "home",
        "total_count": total_count,
        "fake_count": fake_count,
        "real_count": real_count,
        "unverified_count": unverified_count,
        "recent": recent,
        "user_media_labels": user_media_labels,
        "user_media_data": user_media_data,
    })



def _allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


@login_required
@requires_detection_access
def analyze_image(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    if request.method == "GET":
        return render(request, "detection/image_analyze.html", {"user": request.user, "result": None, "active_nav": "image", "media_theme": "image"})

    file = request.FILES.get("image")
    if not file:
        messages.error(request, "Please choose an image to upload.")
        return redirect("detection:analyze_image")

    if not _allowed_image(file.name):
        messages.error(request, "Only JPG, JPEG, and PNG images are supported.")
        return redirect("detection:analyze_image")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    original_filename = os.path.basename(file.name)
    unique_id = uuid.uuid4().hex[:10]
    safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-") or "image.jpg"
    stored_filename = f"{unique_id}_{safe_name}"
    upload_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(upload_path, "wb") as dest:
        for chunk in file.chunks():
            dest.write(chunk)

    from PIL import Image as PILImage
    with PILImage.open(upload_path) as im:
        img_format = im.format
        img_mode = im.mode
        width, height = im.size
    file_size_kb = round(os.path.getsize(upload_path) / 1024, 2)

    prediction = predict_image(upload_path)

    ela_filename = f"ela_{stored_filename.rsplit('.', 1)[0]}.png"
    ela_path = os.path.join(settings.UPLOAD_DIR, ela_filename)
    ela_info = generate_ela_image(upload_path, ela_path)

    gradcam_filename = f"gradcam_{stored_filename.rsplit('.', 1)[0]}.png"
    gradcam_path = os.path.join(settings.UPLOAD_DIR, gradcam_filename)
    try:
        gradcam_info = generate_gradcam(upload_path, gradcam_path)
    except Exception as exc:
        print(f"[GRAD-CAM ERROR] {exc}")
        gradcam_filename = None
        gradcam_info = {"focus_area_pct": None}

    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    detection = Detection.objects.create(
        user=request.user,
        media_type="image",
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=compute_file_hash(upload_path),
        result=prediction["prediction"],
        confidence=prediction["confidence"],
        raw_probability=prediction["probability"],
        ela_filename=ela_filename,
        gradcam_filename=gradcam_filename,
    )
    request.user.register_detection_used()

    from adminpanel.utils import log_activity
    log_activity(
        request,
        user=request.user,
        action="detection_run",
        description=f"Executed Image Deepfake Analysis on '{original_filename}'. Result: {prediction['prediction']} ({prediction['confidence']:.1f}% confidence)."
    )


    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)
    report_data = {
        "filename": original_filename,
        "format": img_format,
        "mode": img_mode,
        "width": width,
        "height": height,
        "file_size_kb": file_size_kb,
        "model_name": settings.MODEL_NAME,
        "model_accuracy": settings.MODEL_ACCURACY,
        "model_roc_auc": settings.MODEL_ROC_AUC,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "probability": prediction["probability"],
        "ela_irregularity_score": ela_info.get("irregularity_score"),
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "user_name": request.user.name,
        "user_email": request.user.email,
        "analyzed_at": analyzed_at,
    }
    build_image_report(
        report_path, report_data,
        image_path=upload_path, ela_path=ela_path,
        gradcam_path=(gradcam_path if gradcam_filename else None),
    )

    detection.report_filename = report_filename
    detection.save()

    result = {
        "detection_id": detection.id,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "probability": prediction["probability"],
        "image_url": f"{settings.MEDIA_URL}uploads/{stored_filename}",
        "ela_url": f"{settings.MEDIA_URL}uploads/{ela_filename}",
        "gradcam_url": f"{settings.MEDIA_URL}uploads/{gradcam_filename}" if gradcam_filename else None,
        "ela_score": ela_info.get("irregularity_score"),
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "filename": original_filename,
        "format": img_format,
        "mode": img_mode,
        "width": width,
        "height": height,
        "file_size_kb": file_size_kb,
        "analyzed_at": analyzed_at,
        "public_id": detection.public_id,
    }
    return render(request, "detection/image_analyze.html", {"user": request.user, "result": result, "active_nav": "image", "media_theme": "image"})



@login_required
def download_report(request, detection_id):
    detection = get_object_or_404(Detection, id=detection_id)
    if detection.user_id != request.user.id and not request.user.is_admin:
        return HttpResponseForbidden("You do not have permission to view this report.")
    if not detection.report_filename:
        raise Http404("Report not found.")
    report_path = os.path.join(settings.REPORT_DIR, detection.report_filename)
    if not os.path.exists(report_path):
        raise Http404("Report file missing.")
    return FileResponse(
        open(report_path, "rb"), as_attachment=True,
        filename=f"deepfake_report_{detection.original_filename}.pdf",
    )


def _get_wifi_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


@login_required
def download_certificate(request, detection_id):
    detection = get_object_or_404(Detection, id=detection_id)
    if detection.user_id != request.user.id and not request.user.is_admin:
        return HttpResponseForbidden("You do not have permission to view this certificate.")
    if not detection.is_verified_authentic:
        return HttpResponseForbidden("A certificate is only available for results verified as authentic.")

    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    relative_path = reverse("detection:verify_certificate", args=[detection.public_id])
    verify_url = request.build_absolute_uri(relative_path)


    cert_data = {
        "filename": detection.original_filename,
        "media_type": detection.media_type,
        "file_hash": detection.file_hash,
        "verdict_label": "VERIFIED AUTHENTIC",
        "confidence": detection.confidence,
        "analyzed_at": timezone.localtime(detection.created_at).strftime("%Y-%m-%d %H:%M IST"),
        "public_id": detection.public_id,
        "verify_url": verify_url,
    }
    cert_filename = f"certificate_{detection.id}_{detection.public_id.hex[:10]}.pdf"
    cert_path = os.path.join(settings.REPORT_DIR, cert_filename)
    build_certificate_pdf(cert_path, cert_data)

    detection.certificate_filename = cert_filename
    detection.save()

    return FileResponse(
        open(cert_path, "rb"), as_attachment=True,
        filename=f"verified_certificate_{detection.original_filename}.pdf",
    )




def verify_certificate(request, public_id):
    """
    Public, no-login verification page. Deliberately shows minimal
    information — verdict, file hash, media type, and date — and never
    the uploader's identity or the actual file content, so this link is
    safe to share or print without exposing anything private.
    """
    detection = get_object_or_404(Detection, public_id=public_id)
    return render(request, "detection/verify_public.html", {
        "detection": detection,
    })


ALLOWED_VIDEO_EXT = {"mp4", "avi", "mov", "mkv", "webm"}


def _allowed_video(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXT


@login_required
@requires_detection_access
def analyze_video(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/video_analyze.html", {
            "user": user, "result": None, "active_nav": "video", "media_theme": "video",
        })

    file = request.FILES.get("video")
    if not file:
        messages.error(request, "Please choose a video to upload.")
        return redirect("detection:analyze_video")

    if not _allowed_video(file.name):
        messages.error(request, "Only MP4, AVI, MOV, MKV, and WEBM videos are supported.")
        return redirect("detection:analyze_video")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    original_filename = os.path.basename(file.name)
    unique_id = uuid.uuid4().hex[:10]
    safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-") or "video.mp4"
    stored_filename = f"{unique_id}_{safe_name}"
    upload_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(upload_path, "wb") as dest:
        for chunk in file.chunks():
            dest.write(chunk)

    try:
        video_meta = get_video_metadata(upload_path)
        frame_bgr = extract_middle_frame(upload_path, video_meta["total_frames"])
    except Exception as exc:
        messages.error(request, f"Could not process this video: {exc}")
        os.remove(upload_path)
        return redirect("detection:analyze_video")

    faces_detected = detect_faces(frame_bgr)
    frame_rgb, normalized_frame = preprocess_frame(frame_bgr)

    prediction = predict_frame(normalized_frame)

    # Save representative frame as a JPEG for display + ELA
    frame_filename = f"frame_{stored_filename.rsplit('.', 1)[0]}.jpg"
    frame_path = os.path.join(settings.UPLOAD_DIR, frame_filename)
    cv2.imwrite(frame_path, frame_bgr)

    ela_filename = f"ela_{stored_filename.rsplit('.', 1)[0]}.png"
    ela_path = os.path.join(settings.UPLOAD_DIR, ela_filename)
    ela_info = generate_video_ela_image(frame_path, ela_path)

    gradcam_filename = f"gradcam_{stored_filename.rsplit('.', 1)[0]}.png"
    gradcam_path = os.path.join(settings.UPLOAD_DIR, gradcam_filename)
    try:
        gradcam_info = generate_video_gradcam(normalized_frame, gradcam_path)
    except Exception as exc:
        print(f"[VIDEO GRAD-CAM ERROR] {exc}")
        gradcam_filename = None
        gradcam_info = {"focus_area_pct": None}

    try:
        forensic = forensic_video_analysis(upload_path)
    except Exception as exc:
        print(f"[VIDEO FORENSICS ERROR] {exc}")
        forensic = {}

    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    detection = Detection.objects.create(
        user=user,
        media_type="video",
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=compute_file_hash(upload_path),
        result=prediction["prediction"],
        confidence=prediction["confidence"],
        raw_probability=prediction["fake_probability"],
        ela_filename=ela_filename,
        gradcam_filename=gradcam_filename,
    )
    user.register_detection_used()

    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)
    report_data = {
        "filename": original_filename,
        "duration_sec": video_meta["duration_sec"],
        "fps": video_meta["fps"],
        "width": video_meta["width"],
        "height": video_meta["height"],
        "total_frames": video_meta["total_frames"],
        "file_size_mb": video_meta["file_size_mb"],
        "faces_detected": faces_detected,
        "model_name": settings.VIDEO_MODEL_NAME,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "fake_probability": prediction["fake_probability"],
        "real_probability": prediction["real_probability"],
        "threshold": prediction["threshold"],
        "ela_irregularity_score": ela_info.get("irregularity_score"),
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "frames_analyzed": forensic.get("frames_analyzed"),
        "average_brightness": forensic.get("average_brightness"),
        "brightness_std": forensic.get("brightness_std"),
        "average_sharpness": forensic.get("average_sharpness"),
        "sharpness_std": forensic.get("sharpness_std"),
        "average_noise": forensic.get("average_noise"),
        "noise_std": forensic.get("noise_std"),
        "average_frame_difference": forensic.get("average_frame_difference"),
        "user_name": user.name,
        "user_email": user.email,
        "analyzed_at": analyzed_at,
    }
    build_video_report(
        report_path, report_data,
        frame_path=frame_path, ela_path=ela_path,
        gradcam_path=(gradcam_path if gradcam_filename else None),
    )

    detection.report_filename = report_filename
    detection.save()

    result = {
        "detection_id": detection.id,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "fake_probability": prediction["fake_probability"],
        "real_probability": prediction["real_probability"],
        "fake_probability_pct": round(prediction["fake_probability"] * 100, 2),
        "real_probability_pct": round(prediction["real_probability"] * 100, 2),
        "threshold": prediction["threshold"],
        "video_url": f"{settings.MEDIA_URL}uploads/{stored_filename}",
        "frame_url": f"{settings.MEDIA_URL}uploads/{frame_filename}",
        "ela_url": f"{settings.MEDIA_URL}uploads/{ela_filename}",
        "gradcam_url": f"{settings.MEDIA_URL}uploads/{gradcam_filename}" if gradcam_filename else None,
        "ela_score": ela_info.get("irregularity_score"),
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "filename": original_filename,
        "faces_detected": faces_detected,
        "duration_sec": video_meta["duration_sec"],
        "fps": video_meta["fps"],
        "width": video_meta["width"],
        "height": video_meta["height"],
        "total_frames": video_meta["total_frames"],
        "file_size_mb": video_meta["file_size_mb"],
        "forensic": forensic,
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/video_analyze.html", {
        "user": user, "result": result, "active_nav": "video", "media_theme": "video",
    })


ALLOWED_AUDIO_EXT = {"wav", "mp3", "flac", "m4a", "ogg", "aac"}


def _allowed_audio(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO_EXT


@login_required
@requires_detection_access
def analyze_audio(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/audio_analyze.html", {
            "user": user, "result": None, "active_nav": "audio", "media_theme": "audio",
        })

    file = request.FILES.get("audio")
    if not file:
        messages.error(request, "Please choose an audio file to upload.")
        return redirect("detection:analyze_audio")

    if not _allowed_audio(file.name):
        messages.error(request, "Only WAV, MP3, FLAC, M4A, OGG, and AAC files are supported.")
        return redirect("detection:analyze_audio")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    original_filename = os.path.basename(file.name)
    unique_id = uuid.uuid4().hex[:10]
    safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-") or "audio.wav"
    stored_filename = f"{unique_id}_{safe_name}"
    upload_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(upload_path, "wb") as dest:
        for chunk in file.chunks():
            dest.write(chunk)

    try:
        audio_meta = get_audio_metadata(upload_path)
        spectrogram = audio_to_spectrogram(upload_path)
        waveform_audio, waveform_sr = load_waveform(upload_path)
    except Exception as exc:
        messages.error(request, f"Could not process this audio file: {exc}")
        os.remove(upload_path)
        return redirect("detection:analyze_audio")

    prediction = predict_audio(spectrogram)

    waveform_filename = f"waveform_{stored_filename.rsplit('.', 1)[0]}.png"
    waveform_path = os.path.join(settings.UPLOAD_DIR, waveform_filename)
    generate_waveform_image(waveform_audio, waveform_sr, waveform_path)

    spectrogram_filename = f"spectrogram_{stored_filename.rsplit('.', 1)[0]}.png"
    spectrogram_path = os.path.join(settings.UPLOAD_DIR, spectrogram_filename)
    generate_spectrogram_image(spectrogram, spectrogram_path)

    gradcam_filename = f"gradcam_{stored_filename.rsplit('.', 1)[0]}.png"
    gradcam_path = os.path.join(settings.UPLOAD_DIR, gradcam_filename)
    try:
        gradcam_info = generate_audio_gradcam(spectrogram, gradcam_path)
    except Exception as exc:
        print(f"[AUDIO GRAD-CAM ERROR] {exc}")
        gradcam_filename = None
        gradcam_info = {"focus_area_pct": None}

    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    detection = Detection.objects.create(
        user=user,
        media_type="audio",
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=compute_file_hash(upload_path),
        result=prediction["prediction"],
        confidence=prediction["confidence"],
        raw_probability=prediction["real_probability"],
        gradcam_filename=gradcam_filename,
    )
    user.register_detection_used()

    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)
    report_data = {
        "filename": original_filename,
        "format": audio_meta["format"],
        "duration_sec": audio_meta["duration_sec"],
        "sample_rate": audio_meta["sample_rate"],
        "channels": audio_meta["channels"],
        "subtype": audio_meta["subtype"],
        "file_size_kb": audio_meta["file_size_kb"],
        "model_name": settings.AUDIO_MODEL_NAME,
        "model_accuracy": settings.AUDIO_MODEL_ACCURACY,
        "model_roc_auc": settings.AUDIO_MODEL_ROC_AUC,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "real_probability": prediction["real_probability"],
        "fake_probability": prediction["fake_probability"],
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "user_name": user.name,
        "user_email": user.email,
        "analyzed_at": analyzed_at,
    }
    build_audio_report(
        report_path, report_data,
        spectrogram_path=spectrogram_path, waveform_path=waveform_path,
        gradcam_path=(gradcam_path if gradcam_filename else None),
    )

    detection.report_filename = report_filename
    detection.save()

    result = {
        "detection_id": detection.id,
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "real_probability": prediction["real_probability"],
        "fake_probability": prediction["fake_probability"],
        "real_probability_pct": round(prediction["real_probability"] * 100, 2),
        "fake_probability_pct": round(prediction["fake_probability"] * 100, 2),
        "audio_url": f"{settings.MEDIA_URL}uploads/{stored_filename}",
        "waveform_url": f"{settings.MEDIA_URL}uploads/{waveform_filename}",
        "spectrogram_url": f"{settings.MEDIA_URL}uploads/{spectrogram_filename}",
        "gradcam_url": f"{settings.MEDIA_URL}uploads/{gradcam_filename}" if gradcam_filename else None,
        "gradcam_focus_pct": gradcam_info.get("focus_area_pct"),
        "filename": original_filename,
        "format": audio_meta["format"],
        "duration_sec": audio_meta["duration_sec"],
        "sample_rate": audio_meta["sample_rate"],
        "channels": audio_meta["channels"],
        "subtype": audio_meta["subtype"],
        "file_size_kb": audio_meta["file_size_kb"],
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/audio_analyze.html", {
        "user": user, "result": result, "active_nav": "audio", "media_theme": "audio",
    })


@login_required
@requires_detection_access
def analyze_text(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/text_analyze.html", {
            "user": user, "result": None, "active_nav": "text", "media_theme": "text",
        })

    text_input = request.POST.get("text_content", "").strip()

    if not text_input:
        messages.error(request, "Please paste some text to analyze.")
        return redirect("detection:analyze_text")

    if len(text_input) < 20:
        messages.error(request, "Please enter at least 20 characters for a meaningful analysis.")
        return redirect("detection:analyze_text")

    metadata = analyze_text_metadata(text_input)
    prediction = predict_text(text_input)
    word_contributions = get_top_contributing_words(text_input)

    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")
    excerpt = text_input[:150] + ("..." if len(text_input) > 150 else "")

    detection = Detection.objects.create(
        user=user,
        media_type="text",
        original_filename=f"Pasted text ({metadata['word_count']} words)",
        stored_filename=None,
        file_hash=compute_text_hash(text_input),
        result=prediction["prediction"],
        confidence=prediction["confidence"],
        raw_probability=prediction["real_probability"],
    )
    user.register_detection_used()

    os.makedirs(settings.REPORT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:10]
    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)

    report_data = {
        "excerpt": excerpt,
        **metadata,
        "model_name": settings.TEXT_MODEL_NAME,
        "model_accuracy": settings.TEXT_MODEL_ACCURACY,
        "model_roc_auc": settings.TEXT_MODEL_ROC_AUC,
        "prediction": prediction["prediction"],
        "prediction_label": prediction["prediction_label"],
        "confidence": prediction["confidence"],
        "real_probability": prediction["real_probability"],
        "fake_probability": prediction["fake_probability"],
        "verdict": prediction["verdict"],
        "user_name": user.name,
        "user_email": user.email,
        "analyzed_at": analyzed_at,
    }
    build_text_report(
        report_path, report_data,
        human_words=word_contributions["human_indicative"],
        ai_words=word_contributions["ai_indicative"],
    )

    detection.report_filename = report_filename
    detection.save()

    result = {
        "detection_id": detection.id,
        "text_content": text_input,
        "excerpt": excerpt,
        "prediction": prediction["prediction"],
        "prediction_label": prediction["prediction_label"],
        "confidence": prediction["confidence"],
        "real_probability": prediction["real_probability"],
        "fake_probability": prediction["fake_probability"],
        "real_probability_pct": round(prediction["real_probability"] * 100, 2),
        "fake_probability_pct": round(prediction["fake_probability"] * 100, 2),
        "verdict": prediction["verdict"],
        "metadata": metadata,
        "human_words": word_contributions["human_indicative"],
        "ai_words": word_contributions["ai_indicative"],
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/text_analyze.html", {
        "user": user, "result": result, "active_nav": "text", "media_theme": "text",
    })


ALLOWED_DOCUMENT_EXT = {"pdf", "jpg", "jpeg", "png"}


def _allowed_document(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXT


@login_required
@requires_detection_access
def analyze_document(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/document_analyze.html", {
            "user": user, "result": None, "active_nav": "document", "media_theme": "document",
            "tesseract_available": TESSERACT_AVAILABLE,
        })

    file = request.FILES.get("document")
    if not file:
        messages.error(request, "Please choose a document to upload.")
        return redirect("detection:analyze_document")

    if not _allowed_document(file.name):
        messages.error(request, "Only PDF, JPG, and PNG files are supported.")
        return redirect("detection:analyze_document")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    original_filename = os.path.basename(file.name)
    unique_id = uuid.uuid4().hex[:10]
    safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-") or "document.pdf"
    stored_filename = f"{unique_id}_{safe_name}"
    upload_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(upload_path, "wb") as dest:
        for chunk in file.chunks():
            dest.write(chunk)

    try:
        file_is_pdf = is_pdf(upload_path)
        if file_is_pdf:
            pdf_meta = analyze_pdf_metadata(upload_path)
            pages = render_pdf_pages(upload_path)
            file_type = "PDF"
        else:
            pdf_meta = None
            pages = load_image_as_page(upload_path)
            file_type = original_filename.rsplit(".", 1)[1].upper()
    except Exception as exc:
        messages.error(request, f"Could not process this document: {exc}")
        os.remove(upload_path)
        return redirect("detection:analyze_document")

    ela_scores = []
    copy_move_results = []
    ocr_texts = []
    page_image_paths = []  # for report + display: (label, url_or_path)

    for i, (page_img, native_text) in enumerate(pages):
        ela_filename = f"docela_{stored_filename.rsplit('.', 1)[0]}_p{i}.png"
        ela_path = os.path.join(settings.UPLOAD_DIR, ela_filename)
        try:
            ela_info = run_ela_on_page(page_img, ela_path)
            ela_scores.append(ela_info["irregularity_score"])
        except Exception as exc:
            print(f"[DOCUMENT ELA ERROR] {exc}")
            ela_filename = None

        cm_filename = f"doccm_{stored_filename.rsplit('.', 1)[0]}_p{i}.png"
        cm_path = os.path.join(settings.UPLOAD_DIR, cm_filename)
        try:
            cm_info = detect_document_copy_move(page_img, cm_path)
            copy_move_results.append(cm_info)
        except Exception as exc:
            print(f"[DOCUMENT COPY-MOVE ERROR] {exc}")
            cm_filename = None
            cm_info = {"suspicious": False, "cluster_size": 0}

        page_text = native_text if native_text else ocr_page(page_img)
        if page_text:
            ocr_texts.append(page_text)

        page_image_paths.append({
            "page_num": i + 1,
            "ela_filename": ela_filename,
            "ela_score": ela_scores[-1] if ela_filename else None,
            "cm_filename": cm_filename,
            "cm_suspicious": cm_info.get("suspicious", False),
            "cm_cluster_size": cm_info.get("cluster_size", 0),
        })

    risk = compute_risk_assessment(pdf_meta, ela_scores, copy_move_results)
    full_text = "\n\n".join(ocr_texts)
    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    # Map risk tier onto the existing REAL/FAKE schema for consistent
    # display across dashboard/history/admin (LOW risk -> REAL-style
    # badge, MEDIUM/HIGH -> FAKE-style badge). The full risk tier and
    # explanation are preserved in the PDF report and result page.
    result_label = "REAL" if risk["risk_tier"] == "LOW" else "FAKE"
    risk_score_pct = round(min(risk["risk_points"], 9) / 9 * 100, 2)

    detection = Detection.objects.create(
        user=user,
        media_type="document",
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=compute_file_hash(upload_path),
        result=result_label,
        confidence=risk_score_pct,
        raw_probability=None,
    )
    user.register_detection_used()

    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)
    report_data = {
        "filename": original_filename,
        "file_type": file_type,
        "page_count": len(pages),
        "pdf_meta": pdf_meta,
        "risk_tier": risk["risk_tier"],
        "verdict": risk["verdict"],
        "risk_points": risk["risk_points"],
        "flags": risk["flags"],
        "ocr_text_preview": full_text[:800] + ("..." if len(full_text) > 800 else "") if full_text else None,
        "user_name": user.name,
        "user_email": user.email,
        "analyzed_at": analyzed_at,
    }
    report_page_images = []
    for p in page_image_paths:
        if p["ela_filename"]:
            report_page_images.append((f"Page {p['page_num']} - Error Level Analysis",
                                        os.path.join(settings.UPLOAD_DIR, p["ela_filename"])))
        if p["cm_filename"] and p["cm_suspicious"]:
            report_page_images.append((f"Page {p['page_num']} - Copy-Move Detection",
                                        os.path.join(settings.UPLOAD_DIR, p["cm_filename"])))

    build_document_report(report_path, report_data, page_images=report_page_images)

    detection.report_filename = report_filename
    detection.save()

    for p in page_image_paths:
        if p["ela_filename"]:
            p["ela_url"] = f"{settings.MEDIA_URL}uploads/{p['ela_filename']}"
        if p["cm_filename"]:
            p["cm_url"] = f"{settings.MEDIA_URL}uploads/{p['cm_filename']}"

    result = {
        "detection_id": detection.id,
        "risk_tier": risk["risk_tier"],
        "verdict": risk["verdict"],
        "risk_points": risk["risk_points"],
        "risk_score_pct": risk_score_pct,
        "flags": risk["flags"],
        "filename": original_filename,
        "file_type": file_type,
        "page_count": len(pages),
        "pdf_meta": pdf_meta,
        "pages": page_image_paths,
        "ocr_text": full_text,
        "tesseract_available": TESSERACT_AVAILABLE,
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/document_analyze.html", {
        "user": user, "result": result, "active_nav": "document", "media_theme": "document",
    })


@login_required
def history(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp
    detections = Detection.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "detection/history.html", {
        "user": request.user, "detections": detections, "active_nav": "history",
    })


@login_required
@requires_detection_access
def analyze_link(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/link_analyze.html", {
            "user": user, "result": None, "active_nav": "link", "media_theme": "link",
        })

    url_input = request.POST.get("url", "").strip()
    if not url_input:
        messages.error(request, "Please enter a URL to check.")
        return redirect("detection:analyze_link")

    analysis = analyze_url(url_input)
    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    result_label = "REAL" if analysis["risk_tier"] == "LOW" else "FAKE"
    risk_score_pct = round(min(analysis["risk_points"], 9) / 9 * 100, 2)

    detection = Detection.objects.create(
        user=user, media_type="link", original_filename=url_input[:250],
        result=result_label, confidence=risk_score_pct,
    )

    os.makedirs(settings.REPORT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:10]
    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)

    build_link_report(report_path, {
        "filename": url_input,
        "host": analysis["host"],
        "risk_tier": analysis["risk_tier"],
        "verdict": analysis["verdict"],
        "risk_points": analysis["risk_points"],
        "flags": analysis["flags"],
        "user_name": user.name,
        "user_email": user.email,
        "analyzed_at": analyzed_at,
    })

    detection.report_filename = report_filename
    detection.save()
    user.register_detection_used()

    result = {
        "detection_id": detection.id,
        "url": url_input,
        "host": analysis["host"],
        "risk_tier": analysis["risk_tier"],
        "verdict": analysis["verdict"],
        "risk_points": analysis["risk_points"],
        "flags": analysis["flags"],
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/link_analyze.html", {
        "user": user, "result": result, "active_nav": "link", "media_theme": "link",
    })


ALLOWED_COMPARE_EXT = {"jpg", "jpeg", "png", "webp", "bmp", "pdf", "txt", "mp3", "wav", "mp4"}


def _allowed_compare_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_COMPARE_EXT


@login_required
@requires_detection_access
def compare_files_view(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user

    if request.method == "GET":
        return render(request, "detection/compare_analyze.html", {
            "user": user, "result": None, "active_nav": "compare", "media_theme": "compare",
        })

    file_a = request.FILES.get("file_a")
    file_b = request.FILES.get("file_b")

    if not file_a or not file_b:
        messages.error(request, "Please choose two files to compare.")
        return redirect("detection:compare_files")

    if not _allowed_compare_file(file_a.name) or not _allowed_compare_file(file_b.name):
        messages.error(request, "Unsupported file type for one or both files.")
        return redirect("detection:compare_files")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)

    unique_id = uuid.uuid4().hex[:10]

    def save_upload(f):
        safe_name = "".join(c for c in f.name if c.isalnum() or c in "._-") or "file"
        stored = f"{uuid.uuid4().hex[:10]}_{safe_name}"
        path = os.path.join(settings.UPLOAD_DIR, stored)
        with open(path, "wb") as dest:
            for chunk in f.chunks():
                dest.write(chunk)
        return path, stored

    path_a, stored_a = save_upload(file_a)
    path_b, stored_b = save_upload(file_b)

    comparison = compare_files(path_a, file_a.name, path_b, file_b.name)
    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")

    # For the REAL/FAKE schema: exact/near-duplicate is flagged as
    # "FAKE"-styled (possible unauthorized reuse); genuinely different
    # files are "REAL"-styled (no duplication concern).
    result_label = "FAKE" if comparison["verdict"] in ("IDENTICAL", "NEAR_DUPLICATE") else "REAL"
    confidence = comparison.get("similarity_pct") if comparison.get("similarity_pct") is not None else (100.0 if comparison["exact_match"] else 0.0)

    detection = Detection.objects.create(
        user=user, media_type="compare",
        original_filename=f"{file_a.name} vs {file_b.name}"[:250],
        result=result_label, confidence=confidence,
    )

    report_filename = f"report_{detection.id}_{unique_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)

    build_compare_report(
        report_path,
        {
            "file_a_name": file_a.name, "file_b_name": file_b.name,
            "verdict": comparison["verdict"], "summary": comparison["summary"],
            "hash_a": comparison["hash_a"], "hash_b": comparison["hash_b"],
            "exact_match": comparison["exact_match"],
            "similarity_pct": comparison.get("similarity_pct"),
            "alignment_a": comparison.get("alignment_a"),
            "alignment_b": comparison.get("alignment_b"),
            "word_metrics": comparison.get("word_metrics"),
            "sentence_metrics": comparison.get("sentence_metrics"),
            "line_page_metrics": comparison.get("line_page_metrics"),
            "user_name": user.name, "user_email": user.email, "analyzed_at": analyzed_at,
        },
        image_a_path=(path_a if is_image_file(file_a.name) else None),
        image_b_path=(path_b if is_image_file(file_b.name) else None),
    )

    detection.report_filename = report_filename
    detection.save()
    user.register_detection_used()

    result = {
        "detection_id": detection.id,
        "file_a_name": file_a.name, "file_b_name": file_b.name,
        "file_a_url": f"{settings.MEDIA_URL}uploads/{stored_a}" if is_image_file(file_a.name) else None,
        "file_b_url": f"{settings.MEDIA_URL}uploads/{stored_b}" if is_image_file(file_b.name) else None,
        "verdict": comparison["verdict"],
        "summary": comparison["summary"],
        "hash_a": comparison["hash_a"],
        "hash_b": comparison["hash_b"],
        "exact_match": comparison["exact_match"],
        "similarity_pct": comparison.get("similarity_pct"),
        "both_images": comparison["both_images"],
        "alignment_a": comparison.get("alignment_a"),
        "alignment_b": comparison.get("alignment_b"),
        "word_metrics": comparison.get("word_metrics"),
        "sentence_metrics": comparison.get("sentence_metrics"),
        "line_page_metrics": comparison.get("line_page_metrics"),
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/compare_analyze.html", {
        "user": user, "result": result, "active_nav": "compare", "media_theme": "compare",
    })


@login_required
@requires_detection_access
def analyze_proctoring(request):
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    user = request.user
    if request.method == "GET":
        return render(request, "detection/proctor_analyze.html", {
            "user": user, "result": None, "active_nav": "proctor", "media_theme": "proctor",
        })

    # Save proctoring session summary & generate PDF certificate report
    session_id = uuid.uuid4().hex[:10]
    integrity_score = int(request.POST.get("integrity_score", 100))
    violations_count = int(request.POST.get("violations_count", 0))
    warnings_raw = request.POST.getlist("warnings[]") or []

    analyzed_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M IST")
    result_label = "REAL" if integrity_score >= 80 else "FAKE"

    detection = Detection.objects.create(
        user=user,
        media_type="proctor",
        original_filename=f"Interview_Proctoring_{session_id}.session",
        result=result_label,
        confidence=float(integrity_score),
    )

    report_filename = f"report_{detection.id}_{session_id}.pdf"
    report_path = os.path.join(settings.REPORT_DIR, report_filename)

    build_proctor_report(
        report_path,
        {
            "session_id": session_id,
            "user_name": user.name,
            "user_email": user.email,
            "integrity_score": integrity_score,
            "violations_count": violations_count,
            "warnings": warnings_raw,
            "analyzed_at": analyzed_at,
        }
    )

    detection.report_filename = report_filename
    detection.save()
    user.register_detection_used()

    result = {
        "detection_id": detection.id,
        "session_id": session_id,
        "integrity_score": integrity_score,
        "violations_count": violations_count,
        "warnings": warnings_raw,
        "analyzed_at": analyzed_at,
    }
    return render(request, "detection/proctor_analyze.html", {
        "user": user, "result": result, "active_nav": "proctor", "media_theme": "proctor",
    })


@login_required
def agentic_assistant(request):
    from .models import AgenticSession
    sessions = AgenticSession.objects.filter(user=request.user)
    current_session = sessions.first()
    if not current_session:
        current_session = AgenticSession.objects.create(
            user=request.user,
            session_id=uuid.uuid4().hex
        )

    messages_qs = current_session.messages.all()

    return render(request, "detection/agentic_assistant.html", {
        "user": request.user,
        "session": current_session,
        "chat_messages": messages_qs,
        "active_nav": "agent",
    })


@login_required
@require_http_methods(["POST"])
def agentic_chat_api(request):
    import json
    from django.http import JsonResponse
    from .models import AgenticSession, AgenticMessage
    from .agentic_core import run_agentic_pipeline

    session_id = request.POST.get("session_id")
    user_text = request.POST.get("message", "").strip()
    uploaded_file = request.FILES.get("media_file")

    session = AgenticSession.objects.filter(user=request.user, session_id=session_id).first()
    if not session:
        session = AgenticSession.objects.create(
            user=request.user,
            session_id=session_id or uuid.uuid4().hex
        )

    if uploaded_file:
        session.media_file = uploaded_file
        session.original_filename = uploaded_file.name
        session.save()

        file_path = session.media_file.path

        # Run multi-tool investigation pipeline
        res = run_agentic_pipeline(file_path, uploaded_file.name, user_prompt=user_text)

        session.detected_media_type = res["media_type"]
        session.summary_verdict = res["verdict"]
        session.save()

        # Save User uploaded file message
        AgenticMessage.objects.create(
            session=session,
            sender="user",
            content=user_text or f"Uploaded '{uploaded_file.name}' for multi-tool forensic inspection."
        )

        # Save Agent Response with thought trace
        agent_msg = AgenticMessage.objects.create(
            session=session,
            sender="agent",
            content=res["summary"],
            thought_trace=res["traces"]
        )

        return JsonResponse({
            "status": "success",
            "detected_media_type": res["media_type"],
            "verdict": res["verdict"],
            "confidence": res["confidence"],
            "reply": res["summary"],
            "traces": res["traces"]
        })

    elif user_text:
        # Save User text query message
        AgenticMessage.objects.create(
            session=session,
            sender="user",
            content=user_text
        )

        # Basic interactive reasoning reply
        reply_content = (
            f"🤖 **VeriScan Agent Investigation Response**\n\n"
            f"I have reviewed your query: *\"{user_text}\"*\n\n"
            f"- **Active Session Format**: `{session.detected_media_type.upper() if session.detected_media_type else 'NO MEDIA UPLOADED'}`\n"
            f"- **Current File**: `{session.original_filename or 'None'}`\n"
            f"- **Verdict Status**: `{session.summary_verdict or 'N/A'}`\n\n"
            f"You can upload any new image, video, audio, or document file at any time to run real-time deepfake analysis."
        )

        agent_msg = AgenticMessage.objects.create(
            session=session,
            sender="agent",
            content=reply_content,
            thought_trace=[
                {"step": 1, "title": "💬 Processing User Query", "detail": f"Analyzed prompt: '{user_text}'"},
                {"step": 2, "title": "📚 Session Context Lookup", "detail": f"Retrieved metadata for session {session.session_id[:8]}"}
            ]
        )

        return JsonResponse({
            "status": "success",
            "reply": reply_content,
            "traces": agent_msg.thought_trace
        })

    return JsonResponse({"status": "error", "message": "No file or message provided."}, status=400)


@login_required
@requires_detection_access
def batch_analyze(request):
    """
    Batch Multi-File Media Deepfake Detection View.
    Accepts multiple uploaded files at once, processes them, and returns a aggregate comparison matrix.
    """
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    if request.method == "GET":
        return render(request, "detection/batch_analyze.html", {
            "user": request.user,
            "active_nav": "batch",
        })

    uploaded_files = request.FILES.getlist("files")
    if not uploaded_files:
        messages.error(request, "Please select at least one file for batch analysis.")
        return redirect("detection:batch_analyze")

    from .agentic_core import run_agentic_pipeline

    batch_results = []
    total_files = len(uploaded_files)
    fake_count = 0
    real_count = 0

    for f in uploaded_files:
        unique_id = uuid.uuid4().hex[:8]
        stored_filename = f"{unique_id}_{f.name}"
        upload_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

        with open(upload_path, "wb+") as destination:
            for chunk in f.chunks():
                destination.write(chunk)

        res = run_agentic_pipeline(upload_path, f.name)

        if res["verdict"] == "FAKE":
            fake_count += 1
        else:
            real_count += 1

        # Create Detection record
        det = Detection.objects.create(
            user=request.user,
            media_type=res["media_type"] if res["media_type"] in ["image", "video", "audio", "document", "text"] else "image",
            original_filename=f.name,
            stored_filename=stored_filename,
            file_hash=compute_file_hash(upload_path),
            result=res["verdict"],
            confidence=res["confidence"],
            raw_probability=res["confidence"] / 100.0,
        )
        request.user.register_detection_used()

        batch_results.append({
            "detection_id": det.id,
            "filename": f.name,
            "media_type": res["media_type"].upper(),
            "verdict": res["verdict"],
            "confidence": res["confidence"],
            "traces": res["traces"],
        })

    from adminpanel.utils import log_activity
    log_activity(
        request,
        user=request.user,
        action="detection_run",
        description=f"Executed Batch Multi-File Detection on {total_files} files ({fake_count} FAKE, {real_count} REAL)."
    )

    return render(request, "detection/batch_analyze.html", {
        "user": request.user,
        "batch_results": batch_results,
        "total_files": total_files,
        "fake_count": fake_count,
        "real_count": real_count,
        "active_nav": "batch",
    })


@login_required
@requires_detection_access
def web_crawler(request):
    """
    Real-Time Deepfake Web & Social Media Crawler View.
    Monitors public news feeds, web URLs, and media sources for target names/brands,
    runs automated deepfake detection, and displays full source citations.
    """
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    from .models import MonitoredTarget, DiscoveredMediaSource
    from .crawler_engine import crawl_and_analyze_target

    targets = MonitoredTarget.objects.filter(user=request.user)
    active_target = None
    discovered_sources = []

    target_id = request.GET.get("target_id")
    if target_id:
        active_target = get_object_or_404(MonitoredTarget, id=target_id, user=request.user)
    elif targets.exists():
        active_target = targets.first()

    if request.method == "POST":
        target_name = request.POST.get("target_name", "").strip()
        category = request.POST.get("category", "Person/Brand").strip()

        if target_name:
            # Create or get monitored target
            target_obj, created = MonitoredTarget.objects.get_or_create(
                user=request.user,
                target_name=target_name,
                defaults={"category": category}
            )

            # Clear old scan items and run new crawler scan
            target_obj.discovered_sources.all().delete()
            crawl_and_analyze_target(target_obj)

            from adminpanel.utils import log_activity
            log_activity(
                request,
                user=request.user,
                action="detection_run",
                description=f"Executed Real-Time Web Crawler scan for target '{target_name}'."
            )

            messages.success(request, f"Web & media scan completed for target '{target_name}'. Public sources retrieved and analyzed.")
            return redirect(f"{reverse('detection:web_crawler')}?target_id={target_obj.id}")

    if active_target:
        discovered_sources = active_target.discovered_sources.all()

    total_sources = len(discovered_sources)
    fake_sources_count = sum(1 for s in discovered_sources if s.deepfake_result == "FAKE")
    real_sources_count = sum(1 for s in discovered_sources if s.deepfake_result == "REAL")

    return render(request, "detection/web_crawler.html", {
        "user": request.user,
        "targets": targets,
        "active_target": active_target,
        "discovered_sources": discovered_sources,
        "total_sources": total_sources,
        "fake_sources_count": fake_sources_count,
        "real_sources_count": real_sources_count,
        "active_nav": "crawler",
    })


@login_required
@requires_detection_access
def job_verifier(request):
    """
    AI Job Role Authenticator & Fake Job Detector View.
    Searches job roles, evaluates posting authenticity (real vs fake scam),
    and renders 'Apply for Job' links for authentic listings.
    """
    redirect_resp = _admin_redirect_if_needed(request.user)
    if redirect_resp:
        return redirect_resp

    from .models import JobSearchQuery, JobListingVerification
    from .job_verifier import search_and_verify_jobs

    searches = JobSearchQuery.objects.filter(user=request.user)
    active_search = None
    listings = []

    search_id = request.GET.get("search_id")
    if search_id:
        active_search = get_object_or_404(JobSearchQuery, id=search_id, user=request.user)
    elif searches.exists():
        active_search = searches.first()

    if request.method == "POST":
        role_query = request.POST.get("role_query", "").strip()

        if role_query:
            search_obj = JobSearchQuery.objects.create(
                user=request.user,
                role_query=role_query
            )

            # Search public job feeds and verify
            raw_listings = search_and_verify_jobs(role_query)

            for item in raw_listings:
                JobListingVerification.objects.create(
                    query=search_obj,
                    job_title=item["job_title"],
                    company_name=item["company_name"],
                    company_domain=item["company_domain"],
                    source_platform=item["source_platform"],
                    location=item["location"],
                    posted_date=item["posted_date"],
                    apply_url=item["apply_url"],
                    status=item["status"],
                    confidence=item["confidence"],
                    scam_indicators=item["scam_indicators"],
                )


            from adminpanel.utils import log_activity
            log_activity(
                request,
                user=request.user,
                action="detection_run",
                description=f"Executed Job Role Authenticator scan for '{role_query}'."
            )

            messages.success(request, f"Job search completed for role '{role_query}'. Listings analyzed for authenticity.")
            return redirect(f"{reverse('detection:job_verifier')}?search_id={search_obj.id}")

    if active_search:
        listings = active_search.listings.all()

    total_listings = len(listings)
    real_jobs_count = sum(1 for l in listings if l.status == "REAL")
    fake_jobs_count = sum(1 for l in listings if l.status == "FAKE")

    return render(request, "detection/job_verifier.html", {
        "user": request.user,
        "searches": searches,
        "active_search": active_search,
        "listings": listings,
        "total_listings": total_listings,
        "real_jobs_count": real_jobs_count,
        "fake_jobs_count": fake_jobs_count,
        "active_nav": "jobs",
    })


@login_required
def recruiter_verifier(request):
    """
    AI Recruiter & Identity Authenticator view.
    Cross-references recruiter names, profile URLs, and contact domains for identity verification.
    """
    searches = RecruiterQuery.objects.filter(user=request.user)
    search_id = request.GET.get("search_id")
    active_search = None
    if search_id:
        active_search = searches.filter(id=search_id).first()
    if not active_search and searches.exists():
        active_search = searches.first()

    verifications = []

    if request.method == "POST":
        recruiter_input = request.POST.get("recruiter_input", "").strip()
        company_name = request.POST.get("company_name", "").strip()

        if recruiter_input:
            search_obj = RecruiterQuery.objects.create(
                user=request.user,
                recruiter_input=recruiter_input,
                company_name=company_name
            )

            # Perform identity verification scan
            raw_verifications = verify_recruiter_profile(recruiter_input, company_name)

            for item in raw_verifications:
                RecruiterVerification.objects.create(
                    query=search_obj,
                    recruiter_name=item["recruiter_name"],
                    claimed_company=item["claimed_company"],
                    profile_url=item["profile_url"],
                    email_domain=item["email_domain"],
                    authenticity_status=item["authenticity_status"],
                    confidence_score=item["confidence_score"],
                    identity_signals=item["identity_signals"],
                    verified_sources=item["verified_sources"],
                )

            from adminpanel.utils import log_activity
            log_activity(
                request,
                user=request.user,
                action="detection_run",
                description=f"Executed Recruiter Identity Verification for '{recruiter_input}'."
            )

            messages.success(request, f"Identity verification complete for '{recruiter_input}'.")
            return redirect(f"{reverse('detection:recruiter_verifier')}?search_id={search_obj.id}")

    if active_search:
        verifications = active_search.verifications.all()

    total_scanned = len(verifications)
    legit_count = sum(1 for v in verifications if v.authenticity_status == "LEGITIMATE")
    suspicious_count = sum(1 for v in verifications if v.authenticity_status != "LEGITIMATE")

    return render(request, "detection/recruiter_verifier.html", {
        "user": request.user,
        "searches": searches,
        "active_search": active_search,
        "verifications": verifications,
        "total_scanned": total_scanned,
        "legit_count": legit_count,
        "suspicious_count": suspicious_count,
        "active_nav": "recruiter",
    })


@login_required
def threat_analytics(request):
    """
    Live Scam & Fraud Threat Analytics Dashboard View.
    Aggregates metrics across deepfake media scans, job authenticity queries,
    and recruiter identity verifications with Chart.js visualizations.
    """
    total_detections = Detection.objects.count()
    fake_media_count = Detection.objects.filter(result="FAKE").count()
    real_media_count = Detection.objects.filter(result="REAL").count()

    total_jobs = JobListingVerification.objects.count()
    fake_jobs_count = JobListingVerification.objects.filter(status="FAKE").count()
    real_jobs_count = JobListingVerification.objects.filter(status="REAL").count()

    total_recruiters = RecruiterVerification.objects.count()
    legit_recruiters_count = RecruiterVerification.objects.filter(authenticity_status="LEGITIMATE").count()
    suspicious_recruiters_count = RecruiterVerification.objects.exclude(authenticity_status="LEGITIMATE").count()

    total_fraud_blocked = fake_media_count + fake_jobs_count + suspicious_recruiters_count
    total_audits_run = total_detections + total_jobs + total_recruiters

    recent_detections = Detection.objects.order_by("-created_at")[:6]
    recent_jobs = JobListingVerification.objects.order_by("-id")[:6]
    recent_recruiters = RecruiterVerification.objects.order_by("-id")[:6]

    return render(request, "detection/threat_analytics.html", {
        "user": request.user,
        "total_audits_run": total_audits_run,
        "total_fraud_blocked": total_fraud_blocked,
        "fake_media_count": fake_media_count,
        "real_media_count": real_media_count,
        "fake_jobs_count": fake_jobs_count,
        "real_jobs_count": real_jobs_count,
        "legit_recruiters_count": legit_recruiters_count,
        "suspicious_recruiters_count": suspicious_recruiters_count,
        "recent_detections": recent_detections,
        "recent_jobs": recent_jobs,
        "recent_recruiters": recent_recruiters,
        "active_nav": "analytics",
    })





