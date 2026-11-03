import os
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import time
from scraper import scrape_page_text
from doc_parser import extract_text
from yt_parser import get_transcript_text
from groq_client import summarize_text, answer_question, summarize_transcript, triage_email
from gmail_client import get_unread_emails, send_email, get_current_account_email
from google_auth import switch_account
from groq_client import compose_email
from fastapi.responses import FileResponse
from doc_generator import build_docx
from sheet_generator import build_xlsx
from groq_client import generate_document, generate_spreadsheet
from websearch import web_search, format_search_context
from stock_data import get_stock_context
from datetime import datetime
from calendar_client import list_upcoming_events, create_event
from groq_client import parse_event_request
from yt_downloader import download_video
from groq_client import summarize_text, answer_question, summarize_transcript, triage_email, compose_email, generate_document, generate_spreadsheet, parse_event_request, chat_reply
from concurrent.futures import ThreadPoolExecutor
from groq_client import triage_emails_batch

app = FastAPI()
templates = Jinja2Templates(directory="templates")
@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")
@app.get("/web-summarizer", response_class=HTMLResponse)
def web_summarizer_page(request: Request):
    return templates.TemplateResponse(request, "web_summarizer.html")
@app.get("/email-triage", response_class=HTMLResponse)
def email_triage_page(request: Request):
    return templates.TemplateResponse(request, "email_triage.html")

class SummarizeRequest(BaseModel):
    url: str

@app.post("/api/summarize")
def api_summarize(req: SummarizeRequest):
    try:
        page_text = scrape_page_text(req.url)
        if not page_text or len(page_text.strip()) < 100:
            return {"status": "failed", "error": "Could not extract readable content from that page."}
        summary = summarize_text(page_text)
        return {"status": "success", "summary": summary}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

@app.get("/doc-summarizer", response_class=HTMLResponse)
def doc_summarizer_page(request: Request):
    return templates.TemplateResponse(request, "doc_summarizer.html")


@app.post("/api/summarize-doc")
async def api_summarize_doc(file: UploadFile = File(...), question: str = Form(None)):
    try:
        file_bytes = await file.read()
        text = extract_text(file.filename, file_bytes)

        if not text or len(text.strip()) < 50:
            return {"status": "failed", "error": "Could not extract readable text from this file."}

        if question:
            answer = answer_question(text, question)
        else:
            answer = summarize_text(text)

        return {"status": "success", "summary": answer}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

@app.get("/youtube-summarizer", response_class=HTMLResponse)
def youtube_summarizer_page(request: Request):
    return templates.TemplateResponse(request, "youtube_summarizer.html")
 
 
class YoutubeSummarizeRequest(BaseModel):
    url: str
 
 
@app.post("/api/summarize-youtube")
def api_summarize_youtube(req: YoutubeSummarizeRequest):
    try:
        transcript = get_transcript_text(req.url)
        if not transcript or len(transcript.strip()) < 50:
            return {"status": "failed", "error": "Could not extract a usable transcript from this video."}
 
        summary = summarize_transcript(transcript)
        return {"status": "success", "summary": summary}
 
    except ValueError as e:
        return {"status": "failed", "error": str(e)}
    except Exception as e:
        return {"status": "failed", "error": str(e)} 

def _triage_one(email):
    # retry a few times in case Groq rate-limits us
    for attempt in range(3):
        try:
            return triage_email(email["from"], email["subject"], email["body"])
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {
        "priority": "normal",
        "reason": "Could not analyze — try scanning again in a minute.",
        "draft_reply": "",
    }


@app.get("/api/triage-emails")
def api_triage_emails():
    try:
        t0 = time.time()
        emails = get_unread_emails(max_results=10)
        print(f"[timing] Gmail fetch: {time.time() - t0:.1f}s, {len(emails)} emails")

        t1 = time.time()
        triage_by_index = {}
        if emails:
            try:
                triage_by_index = triage_emails_batch(emails)
            except Exception as e:
                print(f"[timing] batch failed, falling back: {e}")

        # fallback: any email the batch missed gets triaged one by one
        missing = [i for i in range(len(emails)) if i not in triage_by_index]
        if missing:
            with ThreadPoolExecutor(max_workers=3) as pool:
                fallback = list(pool.map(_triage_one, [emails[i] for i in missing]))
            for i, t in zip(missing, fallback):
                triage_by_index[i] = t
        print(f"[timing] AI triage: {time.time() - t1:.1f}s")

        results = []
        for i, email in enumerate(emails):
            triage = triage_by_index[i]
            results.append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "snippet": email["snippet"],
                "priority": triage["priority"],
                "reason": triage["reason"],
                "draft_reply": triage["draft_reply"],
            })

        priority_order = {"urgent": 0, "normal": 1, "low": 2}
        results.sort(key=lambda e: priority_order.get(e["priority"], 1))

        return {"status": "success", "emails": results}

    except Exception as e:
        return {"status": "failed", "error": str(e)}



@app.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request):
    return templates.TemplateResponse(request, "compose.html")


class ComposeRequest(BaseModel):
    instruction: str


@app.post("/api/compose-draft")
def api_compose_draft(req: ComposeRequest):
    try:
        draft = compose_email(req.instruction)
        return {"status": "success", "draft": draft}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


@app.post("/api/send-email")
def api_send_email(req: SendEmailRequest):
    try:
        if not req.to or "@" not in req.to:
            return {"status": "failed", "error": "That doesn't look like a valid email address."}

        send_email(req.to, req.subject, req.body)
        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
@app.post("/api/switch-account")
def api_switch_account():
    try:
        switch_account()
        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
 
 
@app.get("/api/current-account")
def api_current_account():
    try:
        email = get_current_account_email()
        return {"status": "success", "email": email}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.get("/doc-generator", response_class=HTMLResponse)
def doc_generator_page(request: Request):
    return templates.TemplateResponse(request, "doc_generator.html")
 
 
@app.get("/sheet-generator", response_class=HTMLResponse)
def sheet_generator_page(request: Request):
    return templates.TemplateResponse(request, "sheet_generator.html")

class GenerateRequest(BaseModel):
    instruction: str = ""
    source_text: str = ""
    use_web: bool = False
 
 
@app.post("/api/generate-doc")
def api_generate_doc(req: GenerateRequest):
    try:
        if not req.instruction and not req.source_text:
            return {"status": "failed", "error": "Give an instruction or paste some text first."}
 
        context = ""
        if req.use_web:
            combined = f"{req.instruction} {req.source_text}"
            search_results = web_search(req.instruction or req.source_text, max_results=5)
            context_parts = [format_search_context(search_results), get_stock_context(combined)]
            context = "\n\n".join(p for p in context_parts if p)
 
        content = generate_document(req.instruction, req.source_text, context)
        filename = build_docx(content["title"], content["sections"], content.get("subtitle", ""))
 
        return {
            "status": "success",
            "title": content["title"],
            "subtitle": content.get("subtitle", ""),
            "sections": content["sections"],
            "filename": filename,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}
 
 
@app.post("/api/generate-sheet")
def api_generate_sheet(req: GenerateRequest):
    try:
        if not req.instruction and not req.source_text:
            return {"status": "failed", "error": "Give an instruction or paste some data first."}
 
        context = ""
        if req.use_web:
            combined = f"{req.instruction} {req.source_text}"
            search_results = web_search(req.instruction or req.source_text, max_results=5)
            context_parts = [format_search_context(search_results), get_stock_context(combined)]
            context = "\n\n".join(p for p in context_parts if p)
 
        content = generate_spreadsheet(req.instruction, req.source_text, context)
        filename = build_xlsx(content["sheet_name"], content["headers"], content["rows"])
 
        return {
            "status": "success",
            "sheet_name": content["sheet_name"],
            "headers": content["headers"],
            "rows": content["rows"],
            "filename": filename,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}  

@app.get("/api/test-search")
def api_test_search(q: str):
    try:
        results = web_search(q, max_results=5)
        return {"status": "success", "query": q, "results": results}
    except Exception as e:
        return {"status": "failed", "error": str(e)}  

@app.get("/download/{filename}")
def download_file(filename: str):
    filepath = os.path.join("generated_files", filename)
    if not os.path.exists(filepath):
        return {"status": "failed", "error": "File not found."}

    if filename.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media_type = "application/octet-stream"

    return FileResponse(filepath, filename=filename, media_type=media_type)

@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html")
 
 
# --- ADD THIS ROUTE to list upcoming events ---
 
@app.get("/api/calendar-events")
def api_calendar_events():
    try:
        events = list_upcoming_events(max_results=10)
        return {"status": "success", "events": events}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
 
 
# --- ADD THIS MODEL + ROUTE to create an event from natural language ---
 
class EventRequest(BaseModel):
    instruction: str
 
 
@app.post("/api/create-event")
def api_create_event(req: EventRequest):
    try:
        parsed = parse_event_request(req.instruction)
        if not parsed.get("summary") or not parsed.get("start_datetime"):
            return {"status": "failed", "error": "Could not understand that event request. Try rephrasing with a clearer date/time."}
 
        created = create_event(
            parsed["summary"],
            parsed["start_datetime"],
            parsed["end_datetime"],
            parsed.get("description", ""),
        )
        return {"status": "success", "event": parsed, "link": created.get("htmlLink", "")}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.get("/yt-downloader", response_class=HTMLResponse)
def yt_downloader_page(request: Request):
    return templates.TemplateResponse(request, "yt_downloader.html")
 
 
# --- ADD THIS MODEL + ROUTE ---
 
class YoutubeDownloadRequest(BaseModel):
    url: str
 

@app.get("/exif", response_class=HTMLResponse)
def exif_page(request: Request):
    return templates.TemplateResponse(request, "exif.html")


@app.post("/api/download-video")
def api_download_video(req: YoutubeDownloadRequest):
    try:
        result = download_video(req.url)
        return {"status": "success", "filename": result["filename"], "title": result["title"]}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# --- ADD THESE MODELS + ROUTE anywhere alongside your other @app routes ---
 
class ChatMessage(BaseModel):
    role: str
    content: str
 
 
class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
 
 
@app.post("/api/chat")
def api_chat(req: ChatRequest):
    try:
        search_results = web_search(req.message, max_results=4)
        context = format_search_context(search_results)
 
        history_dicts = [{"role": h.role, "content": h.content} for h in req.history]
        reply = chat_reply(history_dicts, req.message, context)
 
        return {"status": "success", "reply": reply}
    except Exception as e:
        return {"status": "failed", "error": str(e)}