import os
from PIL import Image, ImageEnhance
import re
import json
import html
import io
import time
import urllib.request
from datetime import datetime

MAL_USERNAME = os.environ.get("MAL_USERNAME", "Homuresu")
USER_AGENT = "Mozilla/5.0 (GitHub readme updater)"

# MAL list status codes
READING = 1
COMPLETED = 2

# Max characters each SVG field can hold before running into the next column
TITLE_WIDTH = 22
AUTHOR_WIDTH = 22
PAST_BOOK_WIDTH = 38


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_manga_list(status):
    """Returns the user's MAL manga list for one status, most recently updated first."""
    entries = []
    offset = 0
    while True:
        url = (f"https://myanimelist.net/mangalist/{MAL_USERNAME}/load.json"
               f"?status={status}&order=5&offset={offset}")
        page = json.loads(fetch(url))
        entries.extend(page)
        # MAL returns up to 300 entries per page
        if len(page) < 300:
            return entries
        offset += len(page)
        time.sleep(1)


def fetch_manga_details(manga_id):
    """Scrapes the author and full size cover from the manga's MAL page."""
    page = fetch(f"https://myanimelist.net/manga/{manga_id}").decode("utf-8", errors="replace")

    cover_url = None
    cover_match = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    if cover_match:
        cover_url = cover_match.group(1)

    author = "Unknown"
    authors_match = re.search(r'<span class="dark_text">Authors:</span>(.*?)</div>', page, re.S)
    if authors_match:
        # e.g. <a href="/people/...">Akai, Matsuri</a> (Story)
        authors = re.findall(r'>([^<]+)</a>\s*\(([^)]*)\)', authors_match.group(1))
        if authors:
            # Prefer whoever wrote the story over the artist
            name, _ = next((a for a in authors if "Story" in a[1]), authors[0])
            author = html.unescape(name).replace(", ", " ")

    return author, cover_url


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


def truncate(text, width):
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"

def image_to_ascii(image_path):
    # Use a standard '&' here so we don't mess up row lengths during calculation
    ASCII_CHARS = [" ", ".", ":", ";", "+", "x", "X", "$", "&", "#"]

    try:
        image = Image.open(image_path)
    except Exception as e:
        print(f"Error: Unable to open image. {e}")
        return None

    # 1. Crop image tightly to the center (target the title)
    width, height = image.size
    
    # A. Trim the sides (Crop 15% off the left and right edges)
    # Increase 0.15 to crop closer to the center, decrease to show more edges
    side_margin = int(width * 0.01) 
    left = side_margin
    right = width - side_margin
    
    cropped_width = right - left
    
    # B. Define the height (Make it a rectangle instead of a square)
    # Multiply by a decimal (like 0.6) to make the crop box shorter than it is wide
    cropped_height = int(cropped_width * 0.6) 
    
    # C. Center it vertically
    # To shift the box up or down, add/subtract from this vertical_center variable
    vertical_center = height // 2
    top = vertical_center - (cropped_height // 2)+20
    bottom = vertical_center + (cropped_height // 2)+20
    
    crop_box = (left, top, right, bottom)
    image = image.crop(crop_box)

    # 2. Resize image
    new_width = 50
    
    # Get the actual dimensions of the newly cropped image
    c_width, c_height = image.size
    
    # Find the aspect ratio (how tall it is compared to how wide it is)
    aspect_ratio = c_height / c_width
    
    # Calculate the new height dynamically, keeping the 0.55 font compensator
    new_height = int(new_width * aspect_ratio * 0.55)

    image = image.resize((new_width, new_height))

    # 3. Convert to grayscale and boost contrast
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(3.0)

    # 4. Convert pixels to ASCII
    pixels = list(image.getdata()) 
    ascii_rows = []
    
    divisor = 255 / (len(ASCII_CHARS) - 1)
    
    for i in range(0, len(pixels), new_width):
        row_chars = ""
        for pixel in pixels[i : i + new_width]:
            inverted_value = 255 - pixel
            index = int(inverted_value / divisor)
            index = min(index, len(ASCII_CHARS) - 1)
            
            char = ASCII_CHARS[index]
            
            if char == "&":
                char = "&amp;"
                
            row_chars += char
            
        ascii_rows.append(row_chars)

    return ascii_rows

def update_svg(filename, ascii_art):
    if not os.path.exists(filename):
        print(f"Error: {filename} not found.")
        return

    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    for i in range(len(ascii_art)):
        pattern = rf'(id="books_art{i}">)(.*?)(</tspan>)'
        replacement = rf'\g<1>{ascii_art[i]}\g<3>'
        content = re.sub(pattern, replacement, content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {filename} ASCII art.")

def update_single_svg_text(filename, text_id, new_text):
    """Updates a single tspan by its ID for things like Title and Progress."""
    if not os.path.exists(filename):
        return

    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find the tspan with the matching ID and replace its inner text.
    # Text is XML-escaped (titles like "Assassin & Cinderella") and passed through
    # a function so backslashes in titles aren't treated as regex escapes.
    pattern = rf'(id="{text_id}">)(.*?)(</tspan>)'
    escaped = html.escape(new_text, quote=False)
    content = re.sub(pattern, lambda m: m.group(1) + escaped + m.group(3), content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":

    reading = fetch_manga_list(READING)
    completed = fetch_manga_list(COMPLETED)

    if not reading:
        raise SystemExit(f"No manga marked as reading on {MAL_USERNAME}'s MAL list.")

    # Lists come back most recently updated first, so the top one is what I last read
    current_book = reading[0]
    author, cover_url = fetch_manga_details(current_book["manga_id"])

    chapters = current_book["manga_num_chapters"]
    current_chapter = current_book["num_read_chapters"]

    bar_length = 13
    if chapters:
        percent = min(current_chapter / chapters, 1) * 100
        progress_text = f"{percent:.1f}%"
        filled_blocks = int(min(current_chapter / chapters, 1) * bar_length)
        total_chapters_text = str(chapters)
    else:
        # Still publishing, MAL doesn't know the total yet
        progress_text = "ongoing"
        filled_blocks = 0
        total_chapters_text = "?"
    empty_blocks = bar_length - filled_blocks
    progress_bar = f"[{'█' * filled_blocks}{'-' * empty_blocks}]"

    start_date = parse_mal_date(current_book.get("start_date_string"))
    start_date_text = start_date.strftime("%Y-%m-%d") if start_date else "-"

    # Newest finish date first; entries without one keep their last-updated order after those
    completed.sort(key=lambda e: parse_mal_date(e.get("finish_date_string")) or datetime.min, reverse=True)
    past_books = completed[:10]

    ascii_art = None
    if cover_url:
        ascii_art = image_to_ascii(io.BytesIO(fetch(cover_url)))

    if ascii_art:
        update_svg("darkmode.svg", ascii_art)
        update_svg("lightmode.svg", ascii_art)

    title = display_title(current_book)

    for svg_file in ["darkmode.svg", "lightmode.svg"]:
        # Update Current Book
        update_single_svg_text(svg_file, "book_title", truncate(title, TITLE_WIDTH))
        update_single_svg_text(svg_file, "book_author", truncate(author, AUTHOR_WIDTH))
        update_single_svg_text(svg_file, "book_progress_bar", progress_bar)
        update_single_svg_text(svg_file, "book_progress_text", progress_text)
        update_single_svg_text(svg_file, "book_total_chapters", total_chapters_text)
        update_single_svg_text(svg_file, "book_current_chapter", str(current_chapter))
        update_single_svg_text(svg_file, "book_start_date", start_date_text)

        # Update Past Books, clearing any slots that no longer have a book
        for i in range(10):
            pb_text = ""
            if i < len(past_books):
                pb = past_books[i]
                finish_date = parse_mal_date(pb.get("finish_date_string"))
                suffix = f" ({finish_date.strftime('%m/%d/%Y')})" if finish_date else ""
                prefix = f"{i + 1}. "
                pb_title = truncate(display_title(pb), PAST_BOOK_WIDTH - len(prefix) - len(suffix))
                pb_text = f"{prefix}{pb_title}{suffix}"
            update_single_svg_text(svg_file, f"past_book_{i}", pb_text)
            # Hide the row's bullet too, so empty slots don't leave a stray dot
            update_single_svg_text(svg_file, f"past_book_{i}_bullet", ". " if pb_text else "")

    print(f"Successfully updated SVG with '{title}' at {progress_text}.")