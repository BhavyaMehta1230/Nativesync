import os
import uuid
import yt_dlp

OUTPUT_DIR = "generated_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def download_video(url):
    file_id = uuid.uuid4().hex
    output_template = os.path.join(OUTPUT_DIR, f"{file_id}.%(ext)s")

    ydl_opts = {
        # prefer an already-combined (progressive) stream up to 720p first -- no merge step needed.
        # only fall back to separate video+audio (which needs ffmpeg to merge) if nothing else fits.
        "format": "best[ext=mp4][height<=720]/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best",
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 4,
        # force IPv4. On this network IPv6 hangs for ~100 seconds before falling back,
        # which made every download crawl. This is the same as the --force-ipv4 flag.
        "source_address": "0.0.0.0",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "video")
        raw_filename = ydl.prepare_filename(info)

    base, _ = os.path.splitext(raw_filename)
    final_path = base + ".mp4"
    if not os.path.exists(final_path):
        final_path = raw_filename

    return {"filename": os.path.basename(final_path), "title": title}