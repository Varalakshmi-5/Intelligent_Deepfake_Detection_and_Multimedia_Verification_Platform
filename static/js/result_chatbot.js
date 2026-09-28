/*
 * Result Explainer Chatbot
 * A data-grounded, rule-based assistant (NOT a generic LLM) that answers
 * questions about a specific detection result using the actual numbers
 * from that result — confidence, ELA score, Grad-CAM focus, document
 * flags, etc. This is deliberate: answers are always traceable to real
 * data from the analysis, never invented or hallucinated.
 *
 * Works entirely client-side, no server round-trip, no external AI API.
 */
(function () {
  "use strict";

  function matchChatIntent(question) {
    const q = question.toLowerCase().trim();
    const intents = [
      { key: "why_verdict", patterns: ["why", "how come", "reason", "explain why"] },
      { key: "confidence", patterns: ["confidence", "how sure", "percent", "%"] },
      { key: "ela", patterns: ["ela", "error level", "compression"] },
      { key: "gradcam", patterns: ["grad-cam", "gradcam", "heatmap", "attention", "focus area"] },
      { key: "model", patterns: ["what model", "which model", "algorithm", "how does it work", "how does this work"] },
      { key: "accuracy", patterns: ["accurate", "accuracy", "reliable", "trust", "how good"] },
      { key: "flags", patterns: ["flags", "findings", "what did you find", "issues", "problems detected"] },
      { key: "next_steps", patterns: ["what should i do", "what now", "next step", "report"] },
      { key: "words", patterns: ["which words", "what words", "indicative", "linguistic"] },
      { key: "greeting", patterns: ["hello", "hi ", "hey"] },
      { key: "help", patterns: ["help", "what can you", "what can i ask"] },
    ];
    for (const intent of intents) {
      for (const p of intent.patterns) {
        if (q.includes(p)) return intent.key;
      }
    }
    return "fallback";
  }

  function buildChatAnswer(intentKey, ctx) {
    switch (intentKey) {
      case "why_verdict": {
        const facts = (ctx.extraFacts || []).map(f => `${f.label}: ${f.value}`).join("; ");
        return `Based on my analysis${ctx.filename ? ` of "${ctx.filename}"` : ""}, this was classified as ${ctx.verdictLabel}${ctx.confidence !== null ? ` with ${ctx.confidence}% confidence` : ""}. ${facts ? "Key factors: " + facts : "This matched patterns the model associates with this class."}`;
      }
      case "confidence": {
        if (ctx.confidence === null) return `This module doesn't produce a single confidence percentage — instead it reports a risk level (${ctx.verdict}) based on multiple independent checks, shown in the Findings tab.`;
        return `The model is ${ctx.confidence}% confident in this verdict. This reflects how strongly the input matched patterns the model learned during training — it's a strong signal, not an absolute guarantee.`;
      }
      case "ela": {
        const elaFact = (ctx.extraFacts || []).find(f => f.label.toLowerCase().includes("ela"));
        return elaFact
          ? `Error Level Analysis re-compresses the image and measures the difference. Your result: ${elaFact.value}. Higher scores suggest parts of the image may have been edited or pasted in at a different compression level than the rest.`
          : `Error Level Analysis wasn't part of this particular result.`;
      }
      case "gradcam": {
        const gcFact = (ctx.extraFacts || []).find(f => f.label.toLowerCase().includes("grad-cam") || f.label.toLowerCase().includes("focus"));
        return gcFact
          ? `Grad-CAM shows which part of the input most influenced the model's decision. Here, it focused on ${gcFact.value} of the content.`
          : `Grad-CAM wasn't generated for this result.`;
      }
      case "model": {
        return ctx.modelName
          ? `This used ${ctx.modelName} for the ${ctx.mediaType} analysis.`
          : `This module uses a rule-based forensic pipeline rather than a single trained model — see the Findings tab for exactly what was checked.`;
      }
      case "accuracy": {
        return `No detection model is 100% perfect — treat this result as a strong signal, not absolute proof. I'd recommend cross-checking with the forensic details in the other tabs before making a final decision.`;
      }
      case "flags": {
        if (!ctx.flags || ctx.flags.length === 0) return `No specific flags were raised for this result — the Findings/AI Analysis tab has the full breakdown.`;
        return `Here's what I found: ${ctx.flags.join(" | ")}`;
      }
      case "next_steps": {
        let msg = `You can download the full PDF report for a detailed record`;
        if (ctx.verdict === "REAL" || ctx.verdict === "LOW") msg += `, or grab a Verified Certificate you can share or attach elsewhere`;
        return msg + ".";
      }
      case "words": {
        return (ctx.extraFacts || []).some(f => f.label.toLowerCase().includes("word"))
          ? `Check the Linguistic Analysis tab — it lists the specific words that pushed this toward human vs. AI-generated.`
          : `This isn't a text result, so there's no word-level breakdown here.`;
      }
      case "greeting": {
        return `Hi! I'm here to help explain this ${ctx.mediaType} result. Ask me things like "why was this flagged?" or "what does the confidence score mean?"`;
      }
      case "help": {
        return `You can ask me: why this was flagged, what the confidence score means, what ELA or Grad-CAM show, how accurate the model is, or what to do next.`;
      }
      default:
        return `I don't have a specific answer for that, but here's a quick summary: this ${ctx.mediaType} was classified as ${ctx.verdictLabel}${ctx.confidence !== null ? ` (${ctx.confidence}% confidence)` : ""}. Try asking "why was this flagged?" or "what does confidence mean?"`;
    }
  }

  window.ResultChatbot = { matchChatIntent, buildChatAnswer };

  function initResultChatbot(config) {
    const { context, elements } = config;
    const { toggleBtn, panel, messagesEl, input, sendBtn, closeBtn } = elements;

    function addMessage(text, sender) {
      const bubble = document.createElement("div");
      bubble.className = "chat-bubble chat-" + sender;
      bubble.textContent = text;
      messagesEl.appendChild(bubble);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function handleSend() {
      const question = input.value.trim();
      if (!question) return;
      addMessage(question, "user");
      input.value = "";

      const intent = window.ResultChatbot.matchChatIntent(question);
      const answer = window.ResultChatbot.buildChatAnswer(intent, context);
      setTimeout(() => addMessage(answer, "bot"), 300);
    }

    sendBtn.addEventListener("click", handleSend);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); handleSend(); }
    });

    let opened = false;
    toggleBtn.addEventListener("click", () => {
      panel.classList.toggle("open");
      if (!opened) {
        opened = true;
        addMessage(buildChatAnswer("greeting", context), "bot");
      }
    });
    if (closeBtn) {
      closeBtn.addEventListener("click", () => panel.classList.remove("open"));
    }
  }

  window.initResultChatbot = initResultChatbot;
})();
