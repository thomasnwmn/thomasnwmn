"""Converts a GIF into ASCII frames for the profile card's portrait.

    pip install Pillow
    python gif_to_ascii.py path/to/animation.gif

Writes portrait_frames.json, which render.py animates. Only needs running again
when the GIF changes, so the workflow doesn't need Pillow.
"""
import json
import sys

from PIL import Image, ImageSequence

OUTPUT_FILE = "portrait_frames.json"

# The portrait slot on the card, in characters
COLUMNS = 100
ROWS = 50
# A character cell is 8.2px wide and 15px tall on the card
CELL_ASPECT = 8.2 / 15

# Lightest to darkest: light pixels become sparse characters
ASCII_CHARS = " .:;+xX$&"

# Grey level (0-255) at or above which each character is used, lightest first;
# anything darker than the last one gets the final character. These were fitted
# to the original hand-tuned portrait so new frames keep its look: mostly ';' and
# '+' through the hair, very few '.', and '$' / '&' only on the darkest outlines.
THRESHOLDS = [179, 176, 158, 140, 117, 109, 91, 67]


def to_ascii(frame, columns, rows):
    grey = frame.convert("L").resize((columns, rows), Image.LANCZOS)
    pixels = grey.tobytes()
    lines = []
    for y in range(rows):
        line = ""
        for value in pixels[y * columns:(y + 1) * columns]:
            index = next((i for i, limit in enumerate(THRESHOLDS) if value >= limit), len(THRESHOLDS))
            line += ASCII_CHARS[index]
        lines.append(line)
    return lines


def convert(path):
    image = Image.open(path)
    width, height = image.size

    # Fit the whole frame into the slot without stretching it, centred
    columns = min(COLUMNS, round(ROWS * (width / height) / CELL_ASPECT))
    rows = min(ROWS, round(columns * CELL_ASPECT * (height / width)))
    left = (COLUMNS - columns) // 2
    top = (ROWS - rows) // 2

    frames = []
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        duration = frame.info.get("duration") or 100
        art = to_ascii(frame.convert("RGB"), columns, rows)
        lines = [" " * COLUMNS] * top
        lines += [(" " * left + line).ljust(COLUMNS) for line in art]
        lines += [" " * COLUMNS] * (ROWS - top - rows)
        if frames and frames[-1]["rows"] == lines:
            # Identical to the previous frame once converted: just hold it longer
            frames[-1]["ms"] += duration
        else:
            frames.append({"ms": duration, "rows": lines})
    return frames


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    frames = convert(sys.argv[1])
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"frames": frames}, f, indent=1, ensure_ascii=False)
        f.write("\n")
    total = sum(frame["ms"] for frame in frames)
    print(f"Wrote {len(frames)} frames ({total / 1000:.1f}s loop) to {OUTPUT_FILE}")
