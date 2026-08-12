import re
# pyrefly: ignore [missing-import]
from youtube_transcript_api import YouTubeTranscriptApi
# pyrefly: ignore [missing-import]
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound


def extract_video_id(url):
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not find a valid YouTube video ID in that URL.")


def get_transcript_text(url):
    video_id = extract_video_id(url)

    try:
        ytt_api = YouTubeTranscriptApi()
        fetched_transcript = ytt_api.fetch(video_id)
    except TranscriptsDisabled:
        raise ValueError("This video has captions/transcripts disabled.")
    except NoTranscriptFound:
        raise ValueError("No transcript is available for this video.")

    text = " ".join(snippet.text for snippet in fetched_transcript)
    return text.strip()