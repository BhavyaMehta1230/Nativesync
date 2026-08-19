# NativeSync

**NativeSync** is a lightweight, high-performance multipurpose AI tool suite built with FastAPI and Groq LLMs.

## Features
- **Web Summarizer**: Summarize any article or webpage URL in seconds.
- **Document / PDF Q&A**: Extract text from PDF & DOCX files, generate summaries, or ask targeted questions.
- **YouTube Summarizer**: Fetch auto-transcripts and summarize YouTube videos without watching them.
- **Email Triage**: Scan your unread Gmail inbox, auto-priority tag messages (Urgent / Normal / Low), and generate ready-to-send draft replies.

## Setup & Running Locally

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Create a `.env` file with:
   ```env
   GROQ_API_KEY=your_groq_api_key
   ```

3. **Launch Application**:
   ```bash
   uvicorn main:app --reload
   ```
   Open `http://localhost:8000` in your browser.
