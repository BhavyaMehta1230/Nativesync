import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


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