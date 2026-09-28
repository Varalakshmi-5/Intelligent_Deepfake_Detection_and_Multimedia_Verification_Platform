# VeriScan AI — Intelligent Deepfake Detection & Multimedia Verification

A full-stack Django web app built around your trained EfficientNetB0 deepfake
detection model. Users sign up with email OTP verification, log in, and run
images through the real model to get an AI verdict, forensic analysis
(Error Level Analysis + Grad-CAM), and a downloadable PDF report. Admins get
a separate dashboard to manage users and review every detection made on the
platform.

Video, audio, and text detection are wired up as "coming soon" pages —
ready for you to plug in models later without touching the auth/admin/report
plumbing.

---

## 1. What's included

- **Auth**: signup, 6-digit email OTP verification, login, forgot/reset
  password. Both regular users and the admin log in through the same page.
- **Admin (from `.env`)**: a default admin account is created automatically
  the first time you run migrations, using `ADMIN_EMAIL` / `ADMIN_PASSWORD`
  from `.env`. The admin can change their name/email/password afterwards
  from the in-app **Admin → Settings** page.
- **Dashboard**: after login, users see a menu — Image / Video / Audio / Text / Document
  — with a friendly animated robot up top.
- **Image detection (fully working)**: upload a JPG/PNG, and your actual
  `best_image_deepfake_model.keras` (EfficientNetB0, 91.02% accuracy,
  ROC-AUC 0.98) predicts REAL/FAKE with a confidence score. The page also
  shows:
  - Image Information (format, size, dimensions)
  - AI Analysis (model name, accuracy, raw probability)
  - Forensic Analysis (Error Level Analysis + Grad-CAM attention heatmap)
  - Result Summary
  - A downloadable, fully formatted PDF report
- **Video detection (fully working)**: upload an MP4/AVI/MOV/MKV/WEBM, and
  `video_model.keras` (EfficientNetB0 fine-tuned on FaceForensics++ C23)
  analyzes a representative frame with a tuned 0.62 decision threshold on
  fake-probability. The page shows:
  - Video Information (duration, FPS, resolution, frame count, file size,
    faces detected)
  - AI Analysis (prediction, real/fake probability, threshold)
  - Forensic Analysis: Error Level Analysis + Grad-CAM on the sampled frame,
    plus multi-frame consistency stats (brightness, sharpness, noise,
    frame-to-frame difference sampled across up to 20 frames) — the same
    forensic pipeline from your training notebook
  - A downloadable PDF report
- **Audio detection (fully working)**: upload a WAV/MP3/FLAC/M4A/OGG/AAC file,
  and `audio_model.keras` (custom CNN on Log-Mel spectrograms, 99.93% test
  accuracy, ROC-AUC 1.0000) predicts REAL/FAKE. The page shows:
  - Audio Information (format, duration, sample rate, channels, subtype,
    file size)
  - AI Analysis (prediction, real/fake probability)
  - Forensic Analysis: waveform view, the Log-Mel spectrogram fed to the
    CNN, and a Grad-CAM attention overlay showing which time/frequency
    regions of the spectrogram most influenced the verdict
  - A downloadable PDF report
- **Text detection (fully working)**: paste any text, and
  `text_model.pkl` + `text_vectorizer.pkl` (TF-IDF + Logistic Regression,
  100% test accuracy, ROC-AUC 1.0000 on the training dataset) predicts
  HUMAN/REAL or AI/FAKE. The page shows:
  - Text Content (the submitted text + statistics: word/character/sentence
    counts, average word/sentence length, vocabulary richness, etc.)
  - AI Analysis (prediction, confidence, human vs. AI probability)
  - Linguistic Analysis: the specific words/phrases from your text that
    pushed the model toward "human-written" vs. "AI-generated" — computed
    from each term's TF-IDF weight × the model's learned coefficient, so
    you can see *why* it decided what it decided
  - A downloadable PDF report
  - **Honest caveat, shown directly in the UI**: this model was trained
    and evaluated on a relatively small, narrow dataset that hit 100%
    test accuracy — a common sign of overfitting to that dataset's
    specific style rather than true general-purpose AI-text detection.
    Treat it as one signal, not a certainty, especially on writing styles
    unlike the training data.
- **Document detection (fully working)**: upload a PDF or an image of a
  document (contract, invoice, certificate, ID, etc.). **This is
  deliberately NOT a trained AI classifier** — there's no readily
  available pretrained model for document forgery detection, and
  training one from scratch needs labeled forgery data this project
  doesn't have. Instead it runs a rule-based forensic pipeline, the same
  category of technique real document-forensics tools use:
  - **PDF metadata & revision forensics**: creation/modification dates,
    producer/creator software, a count of incremental updates (PDFs keep
    a hidden revision history — extra saves after the fact is a red
    flag), and digital signature presence
  - **Error Level Analysis** on each page (reuses the same technique from
    the Image detector)
  - **Copy-move forgery detection**: finds duplicated regions pasted
    within the same page (e.g. a copied stamp or signature), using ORB
    keypoints clustered by translation vector and filtered for spatial
    compactness — tuned specifically to avoid false positives on
    legitimate repetitive content like table grids or repeated text
    characters (verified against multiple test documents before shipping)
  - **OCR text extraction** (via Tesseract) for scanned/image-based pages
  - All signals combine into an explicit, explainable risk tier (LOW /
    MEDIUM / HIGH) with a plain-language list of exactly what was found —
    never an invented confidence percentage
  - A downloadable PDF report including all findings and visualizations
  - **System requirement**: OCR needs the Tesseract OCR engine installed
    at the OS level (not just a pip package) — see the setup note below.
    If it's not installed, every other check still works normally; only
    text extraction is skipped, and the UI tells the user so.
- **Admin panel**:
  - Dashboard with stats (total users, verified users, total detections,
    real vs. fake counts, breakdown by media type, recent activity)
  - Manage Users (search, enable/disable, delete — with their name/email
    visible)
  - All Detections (search/filter by media type or result, download any
    user's report as PDF)
  - Admin Settings (edit the admin's own name/email/password)
- Every user also has **My Reports** — their own detection history with PDF
  downloads.
- **Verified Authenticity Certificates**: for any result that comes back
  authentic (REAL for image/video/audio/text, LOW risk for Document), users
  get a "Download Verified Certificate" option — a clean, one-page PDF
  badge with a QR code, separate from the full forensic report. Scanning
  the QR (or visiting the link directly) opens a public, no-login
  verification page confirming the result, SHA-256 file hash, and
  analysis date — deliberately **without** revealing the uploader's
  identity or the file itself, so it's safe to attach to a real
  submission (a job application, a listing, a court filing) or share with
  someone else to independently re-check. Certificates are generated once
  and cached, tied to the exact file via its SHA-256 hash. Only the
  detection's owner or an admin can download the full certificate PDF;
  the public verify link only ever shows the minimal info above.
- **Freemium paywall**: every new user gets **5 free detections** (across
  any media type). After that, they're redirected to a payment page to
  unlock **7 days of unlimited detections for ₹100**. Payment is handled
  via a **simple manual UPI verification flow**, not a payment gateway —
  no Razorpay/Stripe/KYC/transaction fees:
  - The paywall page shows a UPI QR code (generated from your own
    `UPI_ID` in `.env`) — the user scans it and pays directly to your
    UPI account, so money lands in your account with zero platform cut
  - The user then submits their UPI transaction reference number (UTR),
    optionally with a screenshot, from that same page
  - An admin reviews pending requests under **Admin → Payment
    Requests**, checks the UTR against their own bank/UPI app, and
    clicks **Approve** — which instantly grants that user 7 days of
    unlimited access
  - The paywall gates the actual detection views (GET and POST both), so
    a user can't work around it by reloading or resubmitting a form
  - Admins always have unlimited access, and can also directly grant any
    user 7 more days from the Manage Users page without requiring a
    payment at all (e.g. for support/comp cases)
  - Every user can see their own payment history (Payment History in the
    sidebar) and their current status (free detections left, or paid-
    until date) right on their dashboard
  - **Trade-off worth knowing**: because there's no payment gateway,
    there's no automatic "payment confirmed" signal — approval is
    always a manual step by an admin. If you want instant, fully
    automatic unlocking later, that requires a KYC-verified payment
    gateway (Razorpay, Cashfree, etc.), which takes a small fee per
    transaction in exchange for that automation.
  - **Setup note**: works out of the box with payments *disabled* — the
    paywall page shows a clear "payments aren't configured yet" notice
    instead of a broken QR code until you set `UPI_ID` in `.env` (see
    §2 below).
- **VeriBot Voice Assistant**: on the dashboard, a mic button lets users
  navigate by voice instead of clicking through the sidebar. Tap it, and
  VeriBot greets the user by name and asks where they'd like to go — say
  "Image", "check this document", "I have a video", etc., and it speaks
  a confirmation and takes you straight to that module.
  - Built entirely on the **browser's native Web Speech API**
    (SpeechSynthesis for the voice, SpeechRecognition for listening) —
    no external AI/voice service, no API keys, no server round-trip for
    the voice processing itself
  - Understands natural phrasing, not just exact keywords — e.g. "I
    have a pdf", "check this contract", "I wrote an essay" all correctly
    route to the right module. This was tested against dozens of sample
    phrases (including tricky overlapping words like "clip" and
    "recording") before shipping
  - If it mishears you, it asks you to repeat, up to twice, then
    gracefully suggests using the sidebar instead — it never crashes or
    silently does nothing
  - **Browser support**: works in Chrome and Edge (desktop and Android).
    Firefox and Safari have little/no SpeechRecognition support, so the
    widget detects this and shows a plain-language fallback message
    instead of a broken mic button
  - Only shown to regular users, not admins (admins use the full admin
    panel instead)
- **Result Explainer Chatbot**: every result page (Image, Video, Audio,
  Text, Document, Link, Compare) has a chat bubble in the corner that
  answers questions about that specific result — "why was this flagged?",
  "what does the confidence score mean?", "what did the heatmap show?",
  "what are the findings?" — using the actual numbers from that
  analysis.
  - **Deliberately not a generic LLM**: answers are grounded in real,
    stored data from the analysis (confidence, ELA score, Grad-CAM
    focus, document flags, etc.) rather than an AI model that could
    invent plausible-sounding but incorrect explanations. If it doesn't
    have a specific answer, it says so and offers a data-backed summary
    instead of guessing
  - Runs entirely client-side (no server round-trip, no external AI
    API), using the same kind of rule-based intent matching as the
    voice assistant — tested the same way, with dozens of question
    phrasings verified against real result data before shipping
- **Link Safety Checker**: paste a URL, get a LOW/MEDIUM/HIGH risk
  assessment. **The URL is never actually visited** — this is a
  deliberate safety choice: fetching arbitrary user-submitted URLs
  server-side risks SSRF (tricking your server into hitting internal
  infrastructure), so this only inspects the URL's text structure —
  checking for lookalike/typosquatted domains (e.g. "paypal-secure-login.tk"
  correctly flagged as impersonating PayPal, tested against real phishing
  patterns before shipping), the classic "@" redirect trick, punycode
  homograph domains, raw-IP hosts, suspicious TLDs, and more.
- **File Comparison**: upload two files to check if they're identical,
  near-duplicates, or genuinely different. Uses SHA-256 for exact
  matches, plus a perceptual hash (average hash) for images that catches
  near-duplicates a byte-for-byte hash would miss entirely — e.g. the
  same photo resized and recompressed still gets correctly flagged as
  ~97%+ similar, verified with real test images before shipping.
- **Support Chat**: a simple, WhatsApp-style messaging thread between
  each user and the admin team — genuinely useful for exactly the
  scenario you'd expect ("I paid but my access hasn't unlocked yet").
  - Users message from **Support Chat** in the sidebar; admins see every
    conversation under **Admin → Support Chats**, with an unread-count
    badge per user, and can open and reply to any thread
  - Updates automatically every few seconds via lightweight polling, so
    it feels near-real-time without needing WebSockets/Channels/Redis —
    keeping the "just run `manage.py runserver`" simplicity of the rest
    of this project
  - Not true real-time chat (it's poll-based, checking every 4 seconds)
    — worth knowing if you ever need instant delivery at larger scale,
    but plenty responsive for a support inbox

---

## 2. Setup

### Requirements
- Python 3.10+
- ~2 GB free disk space (TensorFlow is the biggest dependency)
- **Tesseract OCR** (system install, only needed for Document text
  extraction — everything else works without it):
  - **Windows**: download the installer from
    https://github.com/UB-Mannheim/tesseract/wiki and make sure it's
    added to your PATH during setup
  - **Mac**: `brew install tesseract`
  - **Linux (Debian/Ubuntu)**: `sudo apt install tesseract-ocr`
  - Verify with `tesseract --version` in a terminal. If this step is
    skipped, the app still runs fine — Document analysis just skips OCR
    and shows a note in the UI that text extraction is unavailable.

### Steps

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Open .env and set:
#   - SECRET_KEY (any long random string)
#   - ADMIN_EMAIL / ADMIN_PASSWORD (your default admin login)
#   - SMTP_* (optional — see "Email / OTP" below)
#   - UPI_ID / UPI_PAYEE_NAME (optional — see "Payments" below)

# 4. Set up the database (also auto-creates the default admin account)
python manage.py migrate

# 5. Run the app
python manage.py runserver

# 6. Open http://127.0.0.1:8000 in your browser
```

That's it — no separate frontend build step. Django serves everything.

---

## 3. Logging in

- **As a user**: click "Sign Up" on the landing page, verify your email
  with the OTP code, then log in.
- **As the admin**: log in with the email/password from `ADMIN_EMAIL` /
  `ADMIN_PASSWORD` in your `.env` file (defaults to
  `admin@example.com` / `Admin@123` if you don't change them). You'll be
  routed straight to the Admin Dashboard instead of the user dashboard.

## 4. Email / OTP delivery

By default, `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD` in `.env` are blank,
so the app runs in **dev mode**: OTP codes are printed to your terminal
*and* shown directly on the verification screen in the browser. This means
you can use the app immediately with zero email setup.

To send real emails, fill in real SMTP credentials in `.env`, for example
a Gmail App Password:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=youraddress@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SMTP_FROM_EMAIL=youraddress@gmail.com
```

Any standard SMTP provider (SendGrid, Mailgun, Amazon SES, etc.) works the
same way.

---

## 5. Payments (manual UPI verification)

Leave `UPI_ID` blank in `.env` and the app runs fine — every user just
gets unlimited free detections, since the paywall only activates once a
real UPI ID is present. When you're ready to turn it on:

1. Open `.env` and set:
   ```
   UPI_ID=yourname@bank
   UPI_PAYEE_NAME=Your Name or Business Name
   ```
   Use your own real UPI ID here (the one linked to your bank account
   via GPay, PhonePe, Paytm, your bank's app, etc.) — this is where
   payments will actually land, directly, with no middleman.
2. Restart the server. The paywall page will now show a real QR code
   that any UPI app can scan to pay you directly.
3. When a user pays and submits their transaction reference number
   (UTR), it shows up under **Admin → Payment Requests** as "Pending
   Review".
4. As the admin, open your own UPI app or bank statement, confirm the
   UTR and amount match a real payment you received, then click
   **Approve**. This instantly grants that user 7 days of unlimited
   access — no further action needed.
5. If a submitted reference doesn't check out, click **Reject** instead
   (optionally with a reason) and the user stays locked out.

Adjust `FREE_DETECTION_LIMIT`, `PAID_ACCESS_DAYS`, and
`PAID_ACCESS_PRICE_INR` in `.env` to change the free tier size, access
window, or price.

**Why manual instead of automatic**: a payment gateway (Razorpay,
Cashfree, etc.) is the only way to get an *automatic* "payment
confirmed" signal your server can trust — and that requires KYC
(business/personal verification) plus a small fee (~2%) per
transaction. This manual flow avoids both entirely, at the cost of
needing an admin to spend a few seconds approving each payment instead
of it happening instantly. If you later want full automation, the
codebase's `accounts.User.grant_paid_week()` method and the
`requires_detection_access` decorator in `billing/decorators.py` are
the two places that matter — everything else stays the same regardless
of how access actually gets granted.

**Security note**: the screenshot upload (optional) and UTR field are
both just evidence for the admin to manually check — the app itself
does not and cannot verify a UPI transaction automatically without a
gateway. Don't rely on this flow if you need instant, unattended
payment processing at scale; it's designed for a single admin
(or small team) manually reviewing a manageable volume of requests.

---

## 6. Project structure

```
deepfake_platform/     Django project settings & root urls
accounts/               Custom User model, OTP model, signup/login/reset views
detection/               Detection model, ML wrapper, forensics, PDF reports,
                          image/video/audio/text/document/link/compare views
adminpanel/               Admin dashboard, manage users, all detections, settings
billing/                 UPI paywall: PaymentRequest model, QR code
                          generation, manual UTR submission/approval flow
support/                 User <-> admin chat: SupportMessage model,
                          threaded messaging with polling-based updates
templates/               All HTML templates (accounts/, detection/, adminpanel/, billing/, support/)
static/css/style.css      App-wide styling
static/js/voice_assistant.js  VeriBot voice assistant (Web Speech API)
static/js/result_chatbot.js   Result-explainer chatbot (data-grounded, rule-based)
ml_model/                 Your trained best_image_deepfake_model.keras,
                          video_model.keras, audio_model.keras,
                          text_model.pkl, and text_vectorizer.pkl
                          (Document detection uses no model file — it's
                          a rule-based pipeline in detection/document_forensics.py)
media/uploads/            Uploaded images + generated ELA/Grad-CAM images (runtime)
media/reports/            Generated PDF reports (runtime)
```

## 7. All seven modules are now live

Image, video, audio, text, document, link safety, and file comparison
detection are all fully wired up — each with its own analysis logic
(trained model or rule-based, as appropriate), its own
forensic/interpretability tab, its own result-explainer chatbot, and its
own PDF report. Detections are stored generically in the `Detection`
model via `media_type`, so the admin panel, history page, and PDF
reports pick up every media type automatically with no admin-side
changes needed.

If you want to swap in a newer/retrained model for any media type later,
just replace the corresponding file in `ml_model/` (same filename) and
restart the server — no code changes needed unless the input shape or
label convention changes.

## 8. Notes on the AI models

### Image — `best_image_deepfake_model.keras`

The bundled model was trained on your dataset using EfficientNetB0
(fine-tuned), with the following reported metrics (surfaced in the AI
Analysis tab and PDF report):

- Test Accuracy: 91.02%
- ROC-AUC: 0.9805
- Label convention: `fake = 0`, `real = 1` (sigmoid output ≥ 0.5 → REAL)

The **Error Level Analysis (ELA)** tab is a classical forensic technique
(re-compresses the image and diffs it against the original) that flags
regions with inconsistent JPEG compression — useful for spotting localized
splicing/editing independent of the neural network's verdict.

The **Grad-CAM** tab visualizes which regions of the image the model
"looked at" most when making its prediction, using the model's last
convolutional layer.

### Video — `video_model.keras`

EfficientNetB0 fine-tuned on FaceForensics++ (C23 compression). Predicts
on a single representative (middle) frame per video, matching your
notebook's `final_video_analysis` design — this is not a full-timeline
average. Label convention: sigmoid output = probability of FAKE, decision
threshold **0.62** (not the default 0.5, per your training notebook).
The Forensic Analysis tab combines ELA + Grad-CAM on that frame with
multi-frame consistency stats (brightness/sharpness/noise/frame-difference
sampled across up to 20 frames).

### Audio — `audio_model.keras`

A custom CNN trained on Log-Mel spectrograms (16kHz, 128 mel bands).
Reported metrics: 99.93% test accuracy, ROC-AUC 1.0000. Label convention:
sigmoid output = probability of REAL, threshold 0.5. The Forensic Analysis
tab shows the waveform, the spectrogram fed to the model, and a Grad-CAM
overlay on the last conv layer (`conv2d_3`).

### Text — `text_model.pkl` + `text_vectorizer.pkl`

TF-IDF (max 10,000 features, 1-2 grams) + Logistic Regression. Reported
metrics: 100% test accuracy, ROC-AUC 1.0000 — **on a small, focused
dataset**, which the app's own UI flags as a likely overfitting signal
rather than a guarantee of general-purpose AI-text detection. Label
convention: class 0 = AI/FAKE, class 1 = HUMAN/REAL. The Linguistic
Analysis tab shows the specific terms from your text that most pushed the
verdict toward human vs. AI, computed from each term's TF-IDF weight ×
the model's learned coefficient — a lightweight, model-native form of
interpretability (no separate library needed).

### Document — rule-based, no model file

Deliberately not a trained classifier — see §1 above for the full
rationale and pipeline (PDF metadata/revision forensics, ELA, copy-move
detection, OCR).

### Link Safety Checker — rule-based, no model file, no network fetch

Purely lexical/structural analysis of the URL string. The URL is
**never visited** — this was a deliberate security decision to avoid
SSRF risk (a server fetching arbitrary user-submitted URLs can be
tricked into hitting internal infrastructure). Checks include: HTTPS
presence, raw-IP hosts, the "@" redirect trick, punycode/homograph
domains, excessive subdomains, known URL shorteners, suspicious TLDs,
and brand-impersonation detection (checking if a well-known brand name
appears in the domain without it actually being that brand's real
domain — e.g. catching `paypal-secure-login.tk` correctly, which a
naive substring check would miss). All of this was tested against
real-world phishing patterns and legitimate sites before shipping,
including fixing a false positive where the brand check was fooled by
domains that merely contain a brand's name.

### File Comparison — SHA-256 + perceptual hash, no model file

SHA-256 catches byte-for-byte identical files. For images specifically,
an average-hash (aHash) perceptual comparison catches near-duplicates a
cryptographic hash would completely miss — e.g. the same photo resized
and recompressed still correctly reports ~97%+ visual similarity, since
aHash compares the image's actual visual structure (a downsampled
grayscale grid) rather than its raw bytes.

---

## 9. Production checklist (before deploying)

This is configured for local/dev use out of the box. Before deploying
publicly:

- Set `DEBUG=False` in `.env`
- Set a strong, unique `SECRET_KEY`
- Set `ALLOWED_HOSTS` to your real domain(s)
- Run `python manage.py collectstatic` and serve static files via your
  web server / CDN
- Switch to a production database if you expect concurrent write load
  (SQLite is fine for small-to-medium usage)
- Configure real SMTP credentials so OTPs are actually emailed
- Put the app behind HTTPS
