"""Fetches the MyAnimeList manga list into the "manga" section of data.json."""
import html
import json
import os
import re
import time
import urllib.request
from datetime import datetime

from profile_data import load_data, load_profile, save_section

USER_AGENT = "Mozilla/5.0 (GitHub readme updater)"

# MAL list status codes
READING = 1
COMPLETED = 2


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_manga_list(username, status):
    """Returns the user's MAL manga list for one status, most recently updated first."""
    entries = []
    offset = 0
    while True:
        url = (f"https://myanimelist.net/mangalist/{username}/load.json"
               f"?status={status}&order=5&offset={offset}")
        page = json.loads(fetch(url))
        entries.extend(page)
        # MAL returns up to 300 entries per page
        if len(page) < 300:
            return entries
        offset += len(page)
        time.sleep(1)


def fetch_author(manga_id):
    """Scrapes the author from the manga's MAL page."""
    page = fetch(f"https://myanimelist.net/manga/{manga_id}").decode("utf-8", errors="replace")
    authors_match = re.search(r'<span class="dark_text">Authors:</span>(.*?)</div>', page, re.S)
    if authors_match:
        # e.g. <a href="/people/...">Akai, Matsuri</a> (Story)
        authors = re.findall(r'>([^<]+)</a>\s*\(([^)]*)\)', authors_match.group(1))
        if authors:
            # Prefer whoever wrote the story over the artist
            name, _ = next((a for a in authors if "Story" in a[1]), authors[0])
            return html.unescape(name).replace(", ", " ")
    return "Unknown"


def parse_mal_date(date_string):
    """MAL list dates come back as MM-DD-YY."""
    if not date_string:
        return None
    try:
        return datetime.strptime(date_string, "%m-%d-%y")
    except ValueError:
        return None


def display_title(entry):
    return html.unescape(entry.get("manga_english") or entry["manga_title"])


def build_section(reading, completed, old):
    current = None
    if reading:
        # Lists come back most recently updated first, so the top one is what I last read
        entry = reading[0]
        old_current = old.get("current") or {}
        if old_current.get("id") == entry["manga_id"] and old_current.get("author", "Unknown") != "Unknown":
            author = old_current["author"]  # no need to scrape the page again
        else:
            author = fetch_author(entry["manga_id"])
        start_date = parse_mal_date(entry.get("start_date_string"))
        current = {
            "id": entry["manga_id"],
            "title": display_title(entry),
            "author": author,
            "chapters": entry.get("manga_num_chapters") or None,
            "read": entry.get("num_read_chapters", 0),
            "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
        }

    # Newest finish date first; entries without one keep their last-updated order after those
    completed = sorted(completed, key=lambda e: parse_mal_date(e.get("finish_date_string")) or datetime.min,
                       reverse=True)
    recent = []
    for entry in completed[:5]:
        finish_date = parse_mal_date(entry.get("finish_date_string"))
        recent.append({"title": display_title(entry),
                       "finish_date": finish_date.strftime("%m/%d/%Y") if finish_date else None})

    scores = [e["score"] for e in reading + completed if e.get("score")]
    stats = {
        "completed": len(completed),
        "reading": len(reading),
        "chapters_read": sum(e.get("num_read_chapters", 0) for e in reading + completed),
        "mean_score": round(sum(scores) / len(scores), 2) if scores else None,
    }
    return {"current": current, "completed": recent, "stats": stats}


if __name__ == "__main__":
    username = os.environ.get("MAL_USERNAME") or load_profile()["mal_username"]
    old = load_data().get("manga", {})
    section = build_section(fetch_manga_list(username, READING), fetch_manga_list(username, COMPLETED), old)
    changed = save_section("manga", section)
    print("Manga data updated." if changed else "Manga data unchanged.")
