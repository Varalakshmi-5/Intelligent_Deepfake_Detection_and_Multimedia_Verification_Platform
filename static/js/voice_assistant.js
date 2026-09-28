/*
 * VeriBot Voice Assistant
 * Uses the browser's native Web Speech API (SpeechSynthesis for
 * text-to-speech, SpeechRecognition for speech-to-text) — no external
 * AI/voice service, no API keys, runs entirely client-side.
 *
 * Browser support: works in Chrome, Edge, and most Chromium-based
 * browsers. Firefox and Safari have little/no SpeechRecognition support
 * as of writing — the widget detects this and shows a graceful fallback.
 */
(function () {
  "use strict";

  function matchIntent(transcript) {
    const text = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();

    const intents = [
      { key: "agent", patterns: ["agent", "agentic", "agentic ai", "copilot", "co pilot", "copilot", "unknown", "auto detect", "ai agent", "auto"] },
      { key: "proctor", patterns: ["proctor", "interview", "proctoring", "exam", "test", "camera"] },
      { key: "document", patterns: ["document", "pdf", "contract", "invoice", "certificate", "paper", "id card", "scan"] },
      { key: "link", patterns: ["link", "url", "website", "phishing"] },
      { key: "compare", patterns: ["compare", "duplicate", "similar files", "two files"] },
      { key: "image", patterns: ["image", "photo", "picture", "pic", "selfie"] },
      { key: "video", patterns: ["video", "movie", "clip", "footage", "film"] },
      { key: "audio", patterns: ["audio", "voice", "sound", "speech", "song", "recording"] },
      { key: "text", patterns: ["text", "article", "essay", "paragraph", "writing", "content"] },
      { key: "history", patterns: ["history", "my reports", "reports", "past", "previous"] },
      { key: "home", patterns: ["home", "dashboard", "back", "main page"] },
    ];

    for (const intent of intents) {
      for (const pattern of intent.patterns) {
        if (text.includes(pattern)) {
          return intent.key;
        }
      }
    }
    return null;
  }


  window.VeriBotIntentMatcher = { matchIntent };

  function initVoiceAssistant(config) {
    const { userName, routes, elements } = config;
    const { micBtn, statusText, transcriptText, container } = elements;

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    const supported = !!SpeechRecognitionCtor && !!window.speechSynthesis;

    if (!supported) {
      statusText.textContent = "Voice assistant isn't supported in this browser. Try Chrome or Edge on desktop/Android.";
      micBtn.disabled = true;
      micBtn.style.opacity = "0.5";
      return;
    }

    let recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let retries = 0;
    const MAX_RETRIES = 2;
    let listening = false;

    function speak(text, onEnd) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      if (onEnd) utterance.onend = onEnd;
      window.speechSynthesis.speak(utterance);
      statusText.textContent = text;
    }

    function startListening() {
      listening = true;
      micBtn.classList.add("listening");
      transcriptText.textContent = "";
      try {
        recognition.start();
      } catch (e) {
        // recognition may already be running; restart cleanly
        recognition.stop();
        setTimeout(() => recognition.start(), 300);
      }
    }

    function stopListening() {
      listening = false;
      micBtn.classList.remove("listening");
      try { recognition.stop(); } catch (e) { /* no-op */ }
    }

    recognition.onresult = function (event) {
      let finalTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        transcriptText.textContent = result[0].transcript;
        if (result.isFinal) finalTranscript = result[0].transcript;
      }

      if (finalTranscript) {
        stopListening();
        handleTranscript(finalTranscript);
      }
    };

    recognition.onerror = function (event) {
      stopListening();
      if (event.error === "no-speech" || event.error === "audio-capture") {
        retryOrGiveUp("I didn't hear anything. Tap the mic to try again.");
      } else if (event.error === "not-allowed") {
        statusText.textContent = "Microphone access was blocked. Please allow microphone permission and try again.";
      } else {
        statusText.textContent = "Something went wrong with voice recognition. Tap the mic to try again.";
      }
    };

    recognition.onend = function () {
      if (listening) stopListening();
    };

    function retryOrGiveUp(message) {
      if (retries < MAX_RETRIES) {
        retries++;
        speak(message, () => startListening());
      } else {
        speak("No problem — you can also just pick a module from the sidebar anytime.");
        retries = 0;
      }
    }

    function handleTranscript(transcript) {
      const intent = matchIntent(transcript);

      if (!intent) {
        retryOrGiveUp(`I didn't quite catch that. You can say Agentic AI, Interview Proctor, Image, Video, Audio, Text, Document, Link Safety, or Compare Files.`);
        return;
      }

      const url = routes[intent];
      if (!url) {
        retryOrGiveUp(`Sorry, I don't have a page for that yet.`);
        return;
      }

      retries = 0;
      const labels = {
        agent: "Agentic AI Co-Pilot", proctor: "AI Interview Proctor",
        image: "Image detection", video: "Video detection", audio: "Audio detection",
        text: "Text detection", document: "Document detection", link: "Link safety check",
        compare: "File comparison", history: "your reports", home: "the dashboard",
      };
      speak(`Got it! Taking you to ${labels[intent] || intent} now.`, () => {
        window.location.href = url;
      });
    }

    micBtn.addEventListener("click", function () {
      if (listening) {
        stopListening();
        window.speechSynthesis.cancel();
        return;
      }
      retries = 0;
      const greeting = `Hi ${userName}! Where would you like to go? You can say Agentic AI, Interview Proctor, Image, Video, Audio, Text, Document, Link Safety, or Compare Files.`;
      speak(greeting, () => startListening());
    });

  }

  window.initVeriBotVoiceAssistant = initVoiceAssistant;

  function speakAnalysisResult(opts) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();

    const verdictText = opts.verdict || "Analysis completed";
    const confidenceText = opts.confidence ? `Confidence score is ${opts.confidence} percent.` : "";
    const modelText = opts.model ? `Detection model used: ${opts.model}.` : "Powered by VeriScan AI Deepfake Detection.";
    const summaryText = opts.summary ? `Summary: ${opts.summary}` : "";

    const textToSpeak = `AI Analysis Completed. Verdict: ${verdictText}. ${confidenceText} ${modelText} ${summaryText}`;

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  window.speakAnalysisResult = speakAnalysisResult;
})();

