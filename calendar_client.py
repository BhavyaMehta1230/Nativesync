from datetime import datetime, timezone
from googleapiclient.discovery import build
from google_auth import get_credentials

DEFAULT_TIMEZONE = "Asia/Kolkata"


def get_calendar_service():
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)


def list_upcoming_events(max_results=10):
    service = get_calendar_service()
    now = datetime.now(timezone.utc).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    result = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        end = e["end"].get("dateTime", e["end"].get("date"))
        result.append({
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": start,
            "end": end,
            "description": e.get("description", ""),
        })
    return result


def create_event(summary, start_datetime, end_datetime, description=""):
    service = get_calendar_service()

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_datetime, "timeZone": DEFAULT_TIMEZONE},
        "end": {"dateTime": end_datetime, "timeZone": DEFAULT_TIMEZONE},
    }

    created = service.events().insert(calendarId="primary", body=event).execute()
    return created