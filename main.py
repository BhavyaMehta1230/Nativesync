from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import time
from scraper import scrape_page_text
from doc_parser import extract_text
from yt_parser import get_transcript_text
from groq_client import summarize_text, answer_question, summarize_transcript, triage_email
from gmail_client import get_unread_emails

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

 
 
# --- ADD THIS ROUTE for the API that fetches + triages emails ---
 
@app.get("/api/triage-emails")
def api_triage_emails():
    try:
        emails = get_unread_emails(max_results=10)

        results = []
        for i, email in enumerate(emails):
            try:
                triage = triage_email(email["from"], email["subject"], email["body"])
            except Exception as e:
                triage = {
                    "priority": "normal",
                    "reason": "Could not analyze — try scanning again in a minute.",
                    "draft_reply": "",
                }

            results.append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "snippet": email["snippet"],
                "priority": triage["priority"],
                "reason": triage["reason"],
                "draft_reply": triage["draft_reply"],
            })

            if i < len(emails) - 1:
                time.sleep(6)

        priority_order = {"urgent": 0, "normal": 1, "low": 2}
        results.sort(key=lambda e: priority_order.get(e["priority"], 1))

        return {"status": "success", "emails": results}

    except Exception as e:
        return {"status": "failed", "error": str(e)}