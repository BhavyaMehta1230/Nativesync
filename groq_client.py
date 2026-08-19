import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"


def _call_groq(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def summarize_text(text):
    prompt = f"""You are summarizing a document for someone who wants the key information fast.

Write your response in this exact format:
1. A short summary (2-3 short paragraphs, plain language, no fluff)
2. A "Key Points" section with 4-6 bullet points covering the most important facts, numbers, and takeaways

Document content:
{text[:15000]}
"""
    return _call_groq(prompt)


def answer_question(text, question):
    prompt = f"""You are answering a question about the following document. Base your answer only on what's actually in the document. If the answer isn't in the document, say so clearly instead of guessing.

Document content:
{text[:15000]}

Question: {question}

Answer:"""
    return _call_groq(prompt)


def summarize_transcript(text):
    prompt = f"""The following is a raw, unpunctuated auto-generated transcript from a YouTube video. It may have no paragraph breaks, awkward wording, or minor transcription errors — work around that and focus on the actual content being discussed.

Write your response in this exact format:
1. A short summary (2-3 short paragraphs, plain language, no fluff)
2. A "Key Points" section with 4-6 bullet points covering the most important facts, arguments, or takeaways from the video

Transcript content:
{text[:15000]}
"""
    return _call_groq(prompt)


def triage_email(sender, subject, body):
    """Reads one email and returns a priority level + a drafted reply, as structured JSON."""
    prompt = f"""You are an email triage assistant. Read the email below and respond with ONLY a valid JSON object, no other text, no markdown formatting, no code fences — just the raw JSON.

The JSON must have exactly these fields:
- "priority": one of "urgent", "normal", or "low"
- "reason": a short (under 15 words) explanation of why you picked that priority
- "draft_reply": a short, polite, ready-to-send draft reply in plain text (2-4 sentences). If the email doesn't need a reply (e.g. a newsletter, notification, or spam-like message), set this to an empty string "" instead.

Email from: {sender}
Subject: {subject}
Body:
{body[:3000]}

Respond with ONLY the JSON object."""

    raw = _call_groq(prompt)

    # models sometimes wrap JSON in code fences despite instructions — strip that defensively
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # fallback if the model didn't return clean JSON — don't crash the whole batch
        result = {
            "priority": "normal",
            "reason": "Could not analyze this email automatically.",
            "draft_reply": "",
        }

    return result