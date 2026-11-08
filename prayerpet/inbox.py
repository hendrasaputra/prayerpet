"""A drop-box folder other programs (Telegram bot, AI assistant, shell) use to talk to the running pet app.

Each request is one small JSON file in ~/.prayerpet-inbox/. The app picks them up about once a second
and deletes them. Kinds: say (text, minutes), feed, pat.
"""
import json
import os
import time

INBOX = os.path.expanduser("~/.prayerpet-inbox")
MAX_TEXT = 280


def clean_text(text):
    text = " ".join(str(text).split())  # collapse newlines/tabs
    text = "".join(ch for ch in text if ch.isprintable())
    return text[:MAX_TEXT]


def post(kind, **fields):
    os.makedirs(INBOX, exist_ok=True)
    if "text" in fields:
        fields["text"] = clean_text(fields["text"])
    data = dict(kind=kind, at=time.time(), **fields)
    name = f"{time.time_ns()}-{kind}.json"
    tmp = os.path.join(INBOX, "." + name)
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, os.path.join(INBOX, name))
    return name


def drain():
    """Return pending requests (oldest first) and delete them."""
    try:
        names = sorted(n for n in os.listdir(INBOX) if n.endswith(".json") and not n.startswith("."))
    except FileNotFoundError:
        return []
    out = []
    for n in names:
        p = os.path.join(INBOX, n)
        try:
            with open(p) as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("kind") in ("say", "feed", "pat"):
                out.append(d)
        except Exception:
            pass
        try:
            os.remove(p)
        except OSError:
            pass
    return out
