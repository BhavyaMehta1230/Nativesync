import os
import json
import time
import requests
from dotenv import load_dotenv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

# "low" makes replies noticeably faster and leaves more room for the actual answer.
# If Groq ever rejects it (a 400 error mentioning reasoning_effort), set this to None.
REASONING_EFFORT = "low"

# Small + fast model used ONLY for email triage (everything else uses MODEL above).
# If Groq ever retires it, pick another small "instant" model from console.groq.com/docs/models
TRIAGE_MODEL = "llama-3.1-8b-instant"

CHUNK_SIZE = 12000   # characters per piece when summarizing long content
MAX_CHUNKS = 3       # ~96k characters max per summary
MAX_RETRIES = 4      # how many times to try when Groq says "too many requests"


# ============================================================
# Low-level API calls (with automatic retry on rate limits)
# ============================================================

def _retry_delay(response, attempt):
    try:
        wait = float(response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        wait = 3 * (2 ** attempt)  # 3s, 6s, 12s...
    return min(max(wait, 1), 30)


def _post_groq(payload, timeout=90):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(MAX_RETRIES):
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 429 and attempt < MAX_RETRIES - 1:
            time.sleep(_retry_delay(response, attempt))
            continue
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        return message.get("content") or ""


def _build_payload(messages, temperature, max_tokens, reasoning_effort, model=None):
    payload = {"model": model or MODEL, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_completion_tokens"] = max_tokens
    if reasoning_effort and model is None:  # only the default (gpt-oss) model accepts this
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _call_groq(prompt, max_tokens=None, reasoning_effort=REASONING_EFFORT, model=None):
    messages = [{"role": "user", "content": prompt}]
    return _post_groq(_build_payload(messages, 0.5, max_tokens, reasoning_effort, model))


def _call_groq_messages(messages):
    return _post_groq(_build_payload(messages, 0.6, None, REASONING_EFFORT))


# ============================================================
# JSON helpers
# ============================================================

def _extract_json(raw):
    """Pulls the first complete {...} object out of a reply, even if it's wrapped in
    code fences or has extra text around it. Raises ValueError if there isn't one."""
    text = (raw or "").strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in reply")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])

    raise ValueError("JSON object was cut off before it finished")


def _safe_json(raw, fallback):
    """For small structured replies: parse the JSON, or return the fallback instead of crashing."""
    try:
        return _extract_json(raw)
    except ValueError:
        return dict(fallback)


def _call_json(prompt, max_tokens=8000):
    """For big structured replies (tables, documents): parse the JSON, retry once with a
    stricter nudge if the first reply is unusable, and raise a clear error if it still fails."""
    last_error = None
    for attempt in range(2):
        nudge = "" if attempt == 0 else (
            "\n\nIMPORTANT: your previous reply was not valid or complete JSON. Reply again with ONLY "
            "one compact JSON object (no extra text, no code fences), and keep it as short as possible."
        )
        raw = _call_groq(prompt + nudge, max_tokens=max_tokens)
        try:
            return _extract_json(raw)
        except ValueError as e:
            last_error = e
    raise ValueError(f"The AI's reply could not be read ({last_error}). Try again, or ask for fewer rows/sections.")


# ============================================================
# Summarizing (handles long content by chunking)
# ============================================================

def _chunk_text(text, chunk_size=CHUNK_SIZE):
    """Splits text into pieces of about chunk_size, preferring to cut at a line break or space."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            floor = start + int(chunk_size * 0.7)
            cut = text.rfind("\n", floor, end)
            if cut == -1:
                cut = text.rfind(" ", floor, end)
            if cut != -1:
                end = cut
        chunks.append(text[start:end])
        start = end
    return chunks


def _summarize_chunk(chunk, index, total):
    prompt = f"""You are reading part {index + 1} of {total} of a longer piece of content. Summarize the key information in this part in 3-5 concise sentences, preserving specific facts, numbers, names, and important details. Just summarize the content itself — don't mention that it's "part of" something.

Content:
{chunk}"""
    return _call_groq(prompt)


def _summarize_long(text, what):
    text = text.strip()

    if len(text) <= CHUNK_SIZE:
        prompt = f"""You are summarizing {what} for someone who wants the key information fast.

Write your response in this exact format:
1. A short summary (2-3 short paragraphs, plain language, no fluff)
2. A "Key Points" section with 4-6 bullet points covering the most important facts, numbers, and takeaways

Content:
{text}
"""
        return _call_groq(prompt)

    all_chunks = _chunk_text(text)
    chunks = all_chunks[:MAX_CHUNKS]

    # 3 at a time (not all at once) so we stay under Groq's free-tier tokens-per-minute limit;
    # anything that still gets rate-limited is retried automatically
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_summarize_chunk, c, i, len(chunks)) for i, c in enumerate(chunks)]
        chunk_summaries = [f.result() for f in futures]

    combined = "\n\n".join(f"Part {i + 1}: {s}" for i, s in enumerate(chunk_summaries))

    final_prompt = f"""You are producing a final, cohesive summary of {what}, based on summaries of its individual sections below.

Write your response in this exact format:
1. A short summary (3-4 short paragraphs, plain language, no fluff, covering the content as a whole)
2. A "Key Points" section with 5-8 bullet points covering the most important facts, numbers, and takeaways from across the entire content

Section summaries:
{combined}
"""
    result = _call_groq(final_prompt)

    if len(all_chunks) > MAX_CHUNKS:
        result += f"\n\n(Note: this was very long, so only the first {MAX_CHUNKS * CHUNK_SIZE:,} characters were summarized.)"
    return result


def summarize_text(text):
    return _summarize_long(
        text,
        "content (it could be an article, a webpage, documentation, code, or any other text — summarize whatever it actually is)",
    )


def summarize_transcript(text):
    return _summarize_long(
        text,
        "a raw, unpunctuated auto-generated YouTube transcript (it may have no paragraph breaks or minor transcription errors — work around that and focus on what's actually being discussed)",
    )


def answer_question(text, question):
    prompt = f"""You are answering a question about the following document. Base your answer only on what's actually in the document. If the answer isn't in the document, say so clearly instead of guessing.

Document content:
{text[:15000]}

Question: {question}

Answer:"""
    return _call_groq(prompt)


# ============================================================
# Email
# ============================================================

def triage_email(sender, subject, body):
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

    raw = _call_groq(prompt, max_tokens=1500, model=TRIAGE_MODEL)
    result = _safe_json(raw, {"priority": "normal", "reason": "Could not analyze this email automatically.", "draft_reply": ""})
    result.setdefault("priority", "normal")
    result.setdefault("reason", "")
    result.setdefault("draft_reply", "")
    return result


def triage_emails_batch(emails):
    """Triage many emails in ONE request. Returns {index: {priority, reason, draft_reply}}."""
    items = []
    for i, e in enumerate(emails):
        items.append(
            f"--- EMAIL {i} ---\nFrom: {e['from']}\nSubject: {e['subject']}\nBody:\n{e['body'][:1200]}"
        )
    joined = "\n\n".join(items)

    prompt = f"""You are an email triage assistant. Below are {len(emails)} emails, numbered from 0. Respond with ONLY a valid JSON object, no other text, no markdown, no code fences.

The JSON must look exactly like this:
{{"results": [{{"index": 0, "priority": "urgent|normal|low", "reason": "...", "draft_reply": "..."}}]}}

Rules:
- Include one entry for EVERY email, using its number as "index".
- "priority" is one of "urgent", "normal", or "low".
- "reason" is under 15 words.
- "draft_reply" is a short, polite, ready-to-send reply (2-4 sentences). Use "" if no reply is needed (newsletters, notifications, spam-like mail).

{joined}

Respond with ONLY the JSON object."""

    raw = _call_groq(prompt, max_tokens=4000, model=TRIAGE_MODEL)
    data = _extract_json(raw)

    out = {}
    for r in data.get("results", []):
        idx = r.get("index")
        if isinstance(idx, int) and 0 <= idx < len(emails):
            out[idx] = {
                "priority": r.get("priority", "normal"),
                "reason": r.get("reason", ""),
                "draft_reply": r.get("draft_reply", ""),
            }
    return out


def compose_email(instruction):
    prompt = f"""You are an email drafting assistant. The user will describe, in natural language, an email they want sent — including who to send it to and what it should say or be about.

Read their instruction and respond with ONLY a valid JSON object, no other text, no markdown formatting, no code fences — just the raw JSON.

The JSON must have exactly these fields:
- "to": the recipient's email address, extracted exactly as written in the instruction. If no email address is mentioned, set this to an empty string "".
- "subject": a short, appropriate subject line for the email (a few words).
- "body": the full email body, written out properly (greeting, content, sign-off if appropriate).

User's instruction: {instruction}

Respond with ONLY the JSON object."""

    raw = _call_groq(prompt, max_tokens=3000)
    result = _safe_json(raw, {"to": "", "subject": "", "body": "Could not generate this draft. Try rephrasing your instruction."})
    result.setdefault("to", "")
    result.setdefault("subject", "")
    result.setdefault("body", "")
    return result


# ============================================================
# Documents and spreadsheets
# ============================================================

def generate_document(instruction, source_text="", context=""):
    """Generates structured content for a Word document, including a subtitle
    and real bullet lists — not just plain paragraphs."""

    if source_text and instruction:
        task = f"""The user pasted the following raw text/notes, and gave this instruction about how to turn it into a document: "{instruction}"

Raw text/notes:
{source_text[:12000]}"""
    elif source_text:
        task = f"""The user pasted the following raw text/notes. Organize and format it into a clean, well-structured, professional document with an appropriate title and section headings.

Raw text/notes:
{source_text[:12000]}"""
    else:
        task = f"""The user wants a professional-quality document written from scratch based on this instruction: "{instruction}" """

    context_block = f"\n\n{context}\n" if context else ""

    prompt = f"""You are a professional document-writing assistant, producing polished business/report-quality documents. {task}
{context_block}
Respond with ONLY a valid JSON object, no other text, no markdown formatting, no code fences — just the raw JSON.

The JSON must have exactly these fields:
- "title": a short, appropriate title for the document
- "subtitle": a short one-line subtitle/tagline that captures what the document is (e.g. "Q3 2026 Sales Performance Report"). Can be an empty string "" if not needed.
- "sections": an array of 3-6 objects, each with:
    - "heading": a clear section heading (can be "" only for a brief intro section with no heading)
    - "content": paragraph text for that section (can include multiple paragraphs separated by double newlines). Use "" if the section is purely a bullet list.
    - "bullets": an array of bullet point strings for this section, where a bulleted breakdown makes sense (key points, action items, findings, features, steps, etc.). Use an empty array [] if the section doesn't need bullets — don't force bullets into every section, only where they genuinely help readability.

Write real, complete, well-organized content — not placeholders, not generic filler. Structure it like an actual professional report or document a business would produce: clear sections, a mix of explanatory paragraphs and bullet lists where appropriate. If real, current data was provided above, use those exact facts/figures instead of estimating or inventing your own. Respond with ONLY the JSON object."""

    result = _call_json(prompt, max_tokens=8000)

    if not isinstance(result.get("sections"), list):
        raise ValueError("The AI's reply was missing the document sections. Try again.")
    result.setdefault("title", "Untitled Document")
    result.setdefault("subtitle", "")
    for sec in result["sections"]:
        sec.setdefault("bullets", [])
        sec.setdefault("content", "")
        sec.setdefault("heading", "")
    return result


def generate_spreadsheet(instruction, source_text="", context=""):
    """Generates structured tabular data for a spreadsheet."""

    if source_text and instruction:
        task = f"""The user pasted the following raw data/text, and gave this instruction about how to turn it into a spreadsheet: "{instruction}"

Raw data/text:
{source_text[:12000]}"""
    elif source_text:
        task = f"""The user pasted the following raw data/text. Organize it into a clean table with appropriate column headers.

Raw data/text:
{source_text[:12000]}"""
    else:
        task = f"""The user wants a spreadsheet built from scratch based on this instruction: "{instruction}" """

    context_block = f"\n\n{context}\n" if context else ""

    prompt = f"""You are a spreadsheet-building assistant. {task}
{context_block}
Respond with ONLY a valid JSON object, no other text, no markdown formatting, no code fences — just the raw JSON.

The JSON must have exactly these fields:
- "sheet_name": a short name for the sheet tab (a few words, no special characters)
- "headers": an array of column header strings
- "rows": an array of arrays, where each inner array is one row of data with values in the same order as the headers. Use realistic, complete data — not placeholders like "Data 1". Numbers should be actual numbers (not strings) where appropriate. Compute derived columns (totals, percentages, grades, ranks, pass/fail) correctly and consistently from the other values in the same row, and generate EVERY row requested.

Keep the JSON compact (no indentation or extra whitespace). If real, current data was provided above (like live prices), use those exact values instead of estimating or inventing your own numbers. Only use the number 0 for a specific data point when real data was genuinely expected but unavailable (e.g. a stock price that couldn't be fetched) — never use 0 to fill cells that don't logically apply, such as a "Shares" or "Price" column on a "Total" summary row; leave those as an empty string "" instead. Respond with ONLY the JSON object."""

    result = _call_json(prompt, max_tokens=8000)

    if not isinstance(result.get("headers"), list) or not isinstance(result.get("rows"), list):
        raise ValueError("The AI's reply was missing the table headers or rows. Try again.")
    result.setdefault("sheet_name", "Sheet1")
    return result


# ============================================================
# Calendar
# ============================================================

def parse_event_request(instruction):
    now = datetime.now()
    now_str = now.strftime("%A, %B %d, %Y %H:%M")

    prompt = f"""You are a calendar assistant. The current date and time is: {now_str}.

The user wants to create a calendar event. Read their instruction and figure out the event title, start time, and end time. If they don't specify a duration, default to 1 hour. If they don't specify a date, assume today. Resolve relative terms like "tomorrow" or "next Friday" based on the current date given above.

Respond with ONLY a valid JSON object, no other text, no markdown formatting, no code fences.

The JSON must have exactly these fields:
- "summary": a short event title
- "start_datetime": start date/time in exactly this format: YYYY-MM-DDTHH:MM:SS (24-hour time, no timezone)
- "end_datetime": end date/time in exactly this format: YYYY-MM-DDTHH:MM:SS (24-hour time, no timezone)
- "description": a short description, can be an empty string ""

User's instruction: {instruction}

Respond with ONLY the JSON object."""

    raw = _call_groq(prompt, max_tokens=3000)
    result = _safe_json(raw, {"summary": "", "start_datetime": "", "end_datetime": "", "description": ""})
    result.setdefault("summary", "")
    result.setdefault("start_datetime", "")
    result.setdefault("end_datetime", "")
    result.setdefault("description", "")
    return result


# ============================================================
# Chat
# ============================================================

def chat_reply(history, user_message, context=""):
    """Multi-turn chat. `history` is a list of {"role": "user"/"assistant", "content": str}.
    `context` is optional live web search results to ground the reply in current info."""

    system_content = (
        "You are NativeSync's built-in AI assistant. Be helpful, direct, and conversational — "
        "like a knowledgeable assistant, not a formal report generator. Keep replies reasonably "
        "concise unless the user is clearly asking for something long or detailed."
    )
    if context:
        system_content += (
            "\n\nHere is real, current information from the web relevant to the user's latest "
            "message. Use it when it's actually relevant to what they asked — don't force it in "
            "if the message is just casual conversation:\n" + context
        )

    messages = [{"role": "system", "content": system_content}]
    for turn in history[-12:]:  # cap how much history we send, keeps requests fast and cheap
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    return _call_groq_messages(messages)