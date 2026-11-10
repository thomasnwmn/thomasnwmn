"""Shared access to profile.json (hand-written content) and data.json (fetched data)."""
import json
from datetime import datetime, timezone

PROFILE_FILE = "profile.json"
DATA_FILE = "data.json"

# Bookkeeping keys that change on every fetch and shouldn't count as "new data"
VOLATILE_KEYS = ("fetched_at",)


def load_profile():
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable(section):
    return {k: v for k, v in (section or {}).items() if k not in VOLATILE_KEYS}


def save_section(name, section):
    """Replaces one section of data.json. "updated" only moves when the content
    actually changed, so the rendered SVG isn't re-committed for nothing."""
    data = load_data()
    changed = _stable(data.get(name)) != _stable(section)
    data[name] = section
    if changed or "updated" not in data:
        data["updated"] = now_iso()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return changed
