import os
from PIL import Image, ImageEnhance
import re
import json

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

    # Regex to find the tspan with the matching ID and replace its inner text
    pattern = rf'(id="{text_id}">)(.*?)(</tspan>)'
    replacement = rf'\g<1>{new_text}\g<3>'
    content = re.sub(pattern, replacement, content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":

    with open("current_book.json", 'r', encoding='utf-8') as f:
        data = json.load(f)

    current_book = data["current_book"]
    past_books = data.get("past_books", [])

    pages = current_book["pages"]
    current_page = current_book["current_page"]

    percent = (current_page / pages) * 100
    progress_text = f"{percent:.1f}%"

    bar_length = 13
    filled_blocks = int((current_page / pages) * bar_length)
    empty_blocks = bar_length - filled_blocks
    progress_bar = f"[{'█' * filled_blocks}{'-' * empty_blocks}]"
    
    image_path = current_book["image_path"]
    ascii_art = image_to_ascii(image_path)

    if ascii_art:
        # Update ASCII Art
        update_svg("darkmode.svg", ascii_art)
        update_svg("lightmode.svg", ascii_art)

        # Update Text Data
        for svg_file in ["darkmode.svg", "lightmode.svg"]:
            # Update Current Book
            update_single_svg_text(svg_file, "book_title", current_book["title"])
            update_single_svg_text(svg_file, "book_author", current_book["author"])
            update_single_svg_text(svg_file, "book_progress_bar", progress_bar)
            update_single_svg_text(svg_file, "book_progress_text", progress_text)
            update_single_svg_text(svg_file, "book_total_pages", str(pages))
            update_single_svg_text(svg_file, "book_current_page", str(current_page))
            
            # Update Past Books (Safely handles up to 3 books)
            for i in range(min(3, len(past_books))):
                pb = past_books[i]
                pb_text = f"{i + 1}. {pb['title']} by {pb['author']} ({pb['completion_date']})"
                update_single_svg_text(svg_file, f"past_book_{i}", pb_text)

        print(f"Successfully updated SVG with '{current_book['title']}' at {progress_text}.")