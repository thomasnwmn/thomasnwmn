"""Renders darkmode.svg and lightmode.svg, the card shown in README.md.

Everything on the card comes from three places:
  profile.json  - the hand-written rows (education, contact, ...)
  portrait_frames.json - the animated ASCII portrait (made by gif_to_ascii.py)
  portrait.txt  - the still ASCII portrait, used when there are no frames
  data.json     - whatever fetch_github.py and fetch_manga.py last fetched

Both themes are built from the same layout, so they can't drift apart.
"""
import html
import json
from datetime import date, datetime, timezone

from profile_data import load_data, load_profile

THEMES = {
    "dark": {
        "bg": "#0A0D12", "text": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff",
        "add": "#3fb950", "del": "#f85149", "cc": "#616e7f", "glow": "#ffffff",
        "heat": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
    "light": {
        "bg": "#d5d8db", "text": "#24292f", "key": "#b04a00", "value": "#0366d6",
        "add": "#22863a", "del": "#cb2431", "cc": "#6a737d", "glow": "#0366d6",
        "heat": ["#c2c7cc", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
}

WIDTH = 1600
LINE = 40            # line pitch of the side text
CHAR_W = 12          # advance of one side-text character (19.9px monospace)

ART_X, ART_Y, ART_PITCH = 15, 30, 15

COL_X = 850          # right-hand column
COL_CHARS = 61       # characters in a full row of it
VALUE_COL = 33       # where left-aligned values start; also the " | " split

# The three columns of the bands under the portrait: (x, width in characters)
BAND_LEFT = (15, 48)
BAND_MID = (600, 41)
BAND_RIGHT = (1104, 38)
BAND_WIDE = (600, 81)

LANGUAGE_BAR_CELLS = 44
LANGUAGE_ROWS = 3    # named languages; the rest are folded into "Other"
OTHER_COLOR = "#8b949e"


# --- text building -----------------------------------------------------------
# A row is a list of (style, text) parts. style is a CSS class, a "#rrggbb"
# fill, or None for the default text colour.

def plen(parts):
    return sum(len(text) for _, text in parts)


def leader(width):
    """A dot leader exactly `width` characters wide, e.g. ' .... '."""
    if width < 3:
        return " " * max(width, 1)
    return " " + "." * (width - 2) + " "


def truncate(text, width):
    text = str(text)
    return text if len(text) <= width else text[:max(width - 1, 0)].rstrip() + "…"


def as_parts(value, style="value"):
    return value if isinstance(value, list) else [(style, str(value))]


def key_head(key):
    """'. Interests.Software:' with each dotted piece in the key colour."""
    parts = [("cc", ". ")]
    for i, piece in enumerate(key.split(".")):
        if i:
            parts.append((None, "."))
        parts.append(("key", piece))
    parts.append((None, ":"))
    return parts


def kv(key, value, value_col):
    """Key, dot leader, then the value starting at `value_col`."""
    head = key_head(key)
    return head + [("cc", leader(value_col - plen(head)))] + as_parts(value)


def kv_right(key, value, end_col, head=None):
    """Key, dot leader, then the value ending at `end_col`."""
    head = head or key_head(key)
    value = as_parts(value)
    return head + [("cc", leader(end_col - plen(head) - plen(value)))] + value


def header(title, width, cursor=False):
    used = len(title) + (1 if cursor else 0) + len(" -") + len("-—-")
    parts = [(None, title)]
    if cursor:
        parts.append(("cursor", "█"))
    parts.append((None, " -" + "—" * max(width - used, 0) + "-—-"))
    return parts


def text_el(x, y, parts, cls="side", extra=""):
    spans = []
    for style, text in parts:
        text = html.escape(text, quote=False)
        if style is None:
            spans.append(text)
        elif style.startswith("#"):
            spans.append(f'<tspan fill="{style}">{text}</tspan>')
        else:
            spans.append(f'<tspan class="{style}">{text}</tspan>')
    return f'<text x="{x}" y="{y}" class="{cls}"{extra}>{"".join(spans)}</text>'


# --- data helpers ------------------------------------------------------------

def parse_iso(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def uptime(created_at, today):
    """Account age in years and months, neofetch style."""
    created = parse_iso(created_at).date()
    months = (today.year - created.year) * 12 + today.month - created.month
    if today.day < created.day:
        months -= 1
    years, months = divmod(max(months, 0), 12)
    pieces = []
    if years:
        pieces.append(plural(years, "year"))
    if months or not years:
        pieces.append(plural(months, "month"))
    return ", ".join(pieces)


def streaks(days):
    """(current, longest) runs of consecutive days with a contribution.
    A day that hasn't had a contribution *yet* doesn't break the current streak."""
    counts = [d["count"] for d in days]
    longest = run = 0
    for count in counts:
        run = run + 1 if count else 0
        longest = max(longest, run)
    if counts and not counts[-1]:
        counts = counts[:-1]
    current = 0
    for count in reversed(counts):
        if not count:
            break
        current += 1
    return current, longest


def language_shares(languages, focus=None):
    """Top languages plus an 'Other' bucket, as (name, colour, fraction).
    With a focus list, only those languages count and the shares are among them."""
    if focus:
        wanted = {name.lower() for name in focus}
        languages = [l for l in languages if l["name"].lower() in wanted]
    languages = sorted(languages, key=lambda l: l["size"], reverse=True)
    total = sum(l["size"] for l in languages)
    if not total:
        return []
    top, rest = languages[:LANGUAGE_ROWS], languages[LANGUAGE_ROWS:]
    if len(rest) == 1:
        top, rest = languages, []
    shares = [(l["name"], l.get("color") or OTHER_COLOR, l["size"] / total) for l in top]
    if rest:
        shares.append(("Other", OTHER_COLOR, sum(l["size"] for l in rest) / total))
    return shares


def bar_cells(fractions, cells):
    """Splits `cells` between the fractions; anything non-zero gets at least one."""
    exact = [f * cells for f in fractions]
    counts = [max(int(e), 1 if e > 0 else 0) for e in exact]
    while sum(counts) < cells:
        i = max(range(len(exact)), key=lambda i: exact[i] - counts[i])
        counts[i] += 1
    while sum(counts) > cells:
        i = max(range(len(counts)), key=lambda i: counts[i] - exact[i] if counts[i] > 1 else -1)
        counts[i] -= 1
    return counts


def number(n):
    return f"{n:,}"


# --- sections ----------------------------------------------------------------

def profile_rows(profile):
    """The hand-written sections of the right column; None is a blank line."""
    rows = [header(profile["prompt"], COL_CHARS, cursor=True)]
    for section in profile["sections"]:
        if section.get("title"):
            rows += [None, header(f"- {section['title']}", COL_CHARS)]
        for row in section["rows"]:
            if row is None:
                rows.append([("cc", ". ")])
            else:
                value = truncate(row[1], COL_CHARS - VALUE_COL)
                rows.append(kv(row[0], value, VALUE_COL))
    return rows


def github_rows(gh, today):
    rows = [None, header("- GitHub Stats", COL_CHARS)]

    def pair(left, right):
        return left + [(None, " | ")] + right

    def right_half(key, value):
        head = [("key", key), (None, ":")]
        return kv_right(key, value, COL_CHARS - VALUE_COL - len(" | "), head=head)

    repos = [("value", str(gh["repos"])), (None, " {"), ("key", "Contributed"), (None, ": "),
             ("value", str(gh["contributed"])), (None, "}")]
    rows.append(pair(kv_right("Repos", repos, VALUE_COL), right_half("Stars", number(gh["stars"]))))
    rows.append(pair(kv_right("Commits", number(gh["commits"]), VALUE_COL),
                     right_half("Followers", number(gh["followers"]))))

    loc = [("value", number(gh["loc_add"] - gh["loc_del"])), (None, " ("),
           ("add", number(gh["loc_add"]) + "++"), (None, ", "),
           ("del", number(gh["loc_del"]) + "--"), (None, ")")]
    rows.append(kv_right("Lines of Code on GitHub", loc, COL_CHARS))

    if gh.get("created_at"):
        rows.append(kv_right("Uptime", uptime(gh["created_at"], today), COL_CHARS))
    return rows


def reading_rows(manga):
    width = BAND_LEFT[1]
    rows = [header("- Currently Reading", width)]
    book = manga.get("current")
    if not book:
        return rows + [[("cc", ". "), ("value", "Nothing right now")]]

    value_col = 26
    room = width - value_col
    chapters, read = book.get("chapters"), book.get("read", 0)
    bar_length = 13
    if chapters:
        fraction = min(read / chapters, 1)
        progress = f"{fraction * 100:.1f}%"
    else:
        # Still publishing, the total isn't known yet
        fraction, progress = 0, "ongoing"
    filled = int(fraction * bar_length)
    bar = f"[{'█' * filled}{'-' * (bar_length - filled)}] {progress}"

    rows.append(kv("Title", truncate(book["title"], room), value_col))
    rows.append(kv("Author", truncate(book.get("author") or "Unknown", room), value_col))
    rows.append(kv("Total Chapters", [("value", str(chapters or "?")), (None, " | "), ("key", "Read"),
                                      (None, ": "), ("value", str(read))], value_col))
    rows.append(kv("Progress", bar, value_col))
    rows.append(kv("Start Date", book.get("start_date") or "-", value_col))
    return rows


def completed_rows(manga):
    width = BAND_MID[1]
    rows = [header("- Recently Completed", width)]
    for i, book in enumerate(manga.get("completed", [])[:5]):
        prefix = f"{i + 1}. "
        suffix = f" ({book['finish_date']})" if book.get("finish_date") else ""
        title = truncate(book["title"], width - len(". ") - len(prefix) - len(suffix))
        rows.append([("cc", ". "), ("value", f"{prefix}{title}{suffix}")])
    return rows


def manga_stats_rows(manga):
    stats = manga.get("stats")
    if not stats:
        return []
    width = BAND_RIGHT[1]
    rows = [header("- Manga Stats", width)]
    rows.append(kv_right("Completed", f"{stats['completed']} series", width))
    rows.append(kv_right("Reading", f"{stats['reading']} series", width))
    rows.append(kv_right("Chapters Read", number(stats["chapters_read"]), width))
    if stats.get("mean_score"):
        rows.append(kv_right("Mean Score", f"{stats['mean_score']:.2f} / 10", width))
    return rows


def language_rows(gh, config):
    shares = language_shares(gh.get("languages", []), config.get("focus"))
    if not shares:
        return []
    width = BAND_LEFT[1]
    rows = [header(f"- {config.get('title', 'Top Languages')}", width)]
    cells = bar_cells([s[2] for s in shares], LANGUAGE_BAR_CELLS)
    bar = [("cc", ". ")] + [(color, "█" * n) for (_, color, _), n in zip(shares, cells) if n]
    rows.append(bar)
    for name, color, fraction in shares:
        head = [("cc", ". "), (color, "██"), (None, " "), ("key", name), (None, ":")]
        rows.append(kv_right(name, f"{fraction * 100:.1f}%", width - 2, head=head))
    return rows


def contribution_block(gh, x, y, theme):
    """Header, heatmap squares and a summary row. Returns SVG elements."""
    calendar = gh.get("calendar")
    if not calendar:
        return []
    width = BAND_WIDE[1]
    out = [text_el(x, y, header("- Contributions (last 12 months)", width))]

    cell, pitch = 14, 18
    days = [day for week in calendar["weeks"] for day in week]
    grid_x = x + 2 * CHAR_W
    grid_y = y + 26
    for w, week in enumerate(calendar["weeks"]):
        for day in week:
            # GitHub weeks start on Sunday
            row = (date.fromisoformat(day["date"]).weekday() + 1) % 7
            out.append(f'<rect x="{grid_x + w * pitch}" y="{grid_y + row * pitch}" width="{cell}" '
                       f'height="{cell}" rx="3" fill="{theme["heat"][day["level"]]}"/>')

    current, longest = streaks(days)
    summary = [("cc", ". "), ("key", "Total"), (None, ": "), ("value", number(calendar["total"])),
               (None, " | "), ("key", "Current Streak"), (None, ": "), ("value", plural(current, "day")),
               (None, " | "), ("key", "Longest"), (None, ": "), ("value", plural(longest, "day"))]
    out.append(text_el(x, y + 5 * LINE, summary))
    return out


# --- page --------------------------------------------------------------------

def style(theme, frame_css=""):
    return f"""
        @font-face {{
            src: local('Consolas'), local('Consolas Bold');
            font-family: 'ConsolasFallback';
            font-display: swap;
            -webkit-size-adjust: 109%;
            size-adjust: 109%;
        }}
        text, tspan {{white-space: pre;}}
        text {{fill: {theme['text']};}}
        .key {{fill: {theme['key']};}}
        .value {{fill: {theme['value']};}}
        .add {{fill: {theme['add']};}}
        .del {{fill: {theme['del']};}}
        .cc {{fill: {theme['cc']};}}
        .side {{font-size: 19.9px;}}
        .note {{font-size: 15px; fill: {theme['cc']};}}

        /* The portrait prints in row by row, then a scanline runs down it now and then */
        .art {{
            letter-spacing: 2px;
            animation: print 0.5s ease-out both, scan 9s linear infinite;
        }}
        @keyframes print {{ from {{opacity: 0;}} to {{opacity: 1;}} }}
        @keyframes scan {{
            0%, 5%, 100% {{fill: {theme['text']};}}
            2.5% {{fill: {theme['glow']};}}
        }}
        .cursor {{fill: {theme['value']}; animation: blink 1.1s steps(1) infinite;}}
        @keyframes blink {{ 50% {{fill-opacity: 0;}} }}

        /* Animated portrait: every frame is stacked in place and shown in turn */
        .frame {{letter-spacing: 2px; opacity: 0; animation-timing-function: steps(1); animation-iteration-count: infinite;}}
        {frame_css}
        @media (prefers-reduced-motion: reduce) {{
            .art, .cursor, .frame {{animation: none !important;}}
            .frame.first {{opacity: 1;}}
        }}
    """


def frame_keyframes(frames):
    """One keyframe set per frame: visible only during its own slice of the loop."""
    total = sum(frame["ms"] for frame in frames)
    rules, start = [], 0
    for i, frame in enumerate(frames):
        a, b = 100 * start / total, 100 * (start + frame["ms"]) / total
        steps = [f"0% {{opacity: {1 if i == 0 else 0};}}"]
        if i:
            steps.append(f"{a:.3f}% {{opacity: 1;}}")
        if b < 100:
            steps.append(f"{b:.3f}% {{opacity: 0;}}")
        rules.append(f"@keyframes f{i} {{ {' '.join(steps)} }}")
        start += frame["ms"]
    return "\n        ".join(rules), total


def frame_el(index, frame, total_ms):
    """A whole frame as one <text>, one <tspan> per row."""
    rows = "".join(f'<tspan x="{ART_X}" y="{ART_Y + i * ART_PITCH}">{html.escape(row.rstrip(), quote=False)}</tspan>'
                   for i, row in enumerate(frame["rows"]) if row.strip())
    cls = "frame first" if index == 0 else "frame"
    return f'<text class="{cls}" style="animation-name: f{index}; animation-duration: {total_ms}ms">{rows}</text>'


def description(profile, gh, manga):
    lines = []
    for section in profile["sections"]:
        lines += [f"{row[0].replace('.', ' ')}: {row[1]}." for row in section["rows"] if row]
    lines.append(f"GitHub: {gh['repos']} repositories, {number(gh['commits'])} commits, "
                 f"{gh['stars']} stars, {gh['followers']} followers.")
    if manga.get("current"):
        lines.append(f"Currently reading {manga['current']['title']}.")
    return " ".join(lines)


def render(theme_name, profile, data, portrait, today, frames=None):
    theme = THEMES[theme_name]
    gh, manga = data["github"], data["manga"]
    body = []

    frame_css = ""
    if frames:
        frame_css, total_ms = frame_keyframes(frames)
        body += [frame_el(i, frame, total_ms) for i, frame in enumerate(frames)]
        portrait = frames[0]["rows"]
    else:
        # Still portrait: one <text> per row so each can be animated on its own
        for i, row in enumerate(portrait):
            delays = f"{i * 40}ms, {3000 + i * 45}ms"
            body.append(text_el(ART_X, ART_Y + i * ART_PITCH, [(None, row)], cls="art",
                                extra=f' style="animation-delay: {delays}"'))
    art_bottom = ART_Y + (len(portrait) - 1) * ART_PITCH

    # Right column
    y = 30
    for row in profile_rows(profile) + github_rows(gh, today):
        if row is not None:
            body.append(text_el(COL_X, y, row))
        y += LINE
    column_bottom = y - LINE

    def band(top, columns):
        for (x, _), rows in columns:
            for i, row in enumerate(rows):
                body.append(text_el(x, top + i * LINE, row))

    band_1 = max(art_bottom, column_bottom) + 50
    band(band_1, [(BAND_LEFT, reading_rows(manga)), (BAND_MID, completed_rows(manga)),
                  (BAND_RIGHT, manga_stats_rows(manga))])

    bottom = band_1 + 5 * LINE
    band_2 = bottom + 80
    languages = language_rows(gh, profile.get("languages", {}))
    contributions = contribution_block(gh, BAND_WIDE[0], band_2, theme)
    if languages or contributions:
        band(band_2, [(BAND_LEFT, languages)])
        body += contributions
        bottom = band_2 + 5 * LINE

    footer_y = bottom + 45
    sample = sorted(set(gh.get("sample", []) + manga.get("sample", [])))
    if sample:
        body.append(f'<text x="15" y="{footer_y}" class="note">preview only, sample data for: '
                    f'{html.escape(", ".join(sample))}</text>')
    if data.get("updated"):
        stamp = parse_iso(data["updated"]).strftime("%Y-%m-%d %H:%M UTC")
        body.append(f'<text x="{WIDTH - 15}" y="{footer_y}" class="note" text-anchor="end">'
                    f'last updated {stamp}</text>')
    height = footer_y + 25

    title = html.escape(f"{profile['name']}'s GitHub profile card")
    desc = html.escape(description(profile, gh, manga))
    inner = "\n    ".join(body)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="{WIDTH}px" height="{height}px" viewBox="0 0 {WIDTH} {height}" xmlns="http://www.w3.org/2000/svg" xml:space="preserve" role="img" aria-labelledby="card-title card-desc" font-size="10.3px" font-family="ConsolasFallback,Consolas,monospace">
    <title id="card-title">{title}</title>
    <desc id="card-desc">{desc}</desc>
    <style>{style(theme, frame_css)}</style>
    <rect width="100%" height="100%" fill="{theme['bg']}" rx="15"/>
    {inner}
</svg>
"""


if __name__ == "__main__":
    profile = load_profile()
    data = load_data()
    if "github" not in data or "manga" not in data:
        raise SystemExit("data.json is missing; run fetch_github.py and fetch_manga.py first.")
    with open("portrait.txt", "r", encoding="utf-8") as f:
        portrait = f.read().rstrip("\n").split("\n")
    try:
        with open("portrait_frames.json", "r", encoding="utf-8") as f:
            frames = json.load(f)["frames"]
    except OSError:
        frames = None

    today = datetime.now(timezone.utc).date()
    for theme_name in THEMES:
        filename = f"{theme_name}mode.svg"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(render(theme_name, profile, data, portrait, today, frames))
        print(f"Rendered {filename}")
